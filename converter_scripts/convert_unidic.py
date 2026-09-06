import os
import csv
import re
import sys
import argparse
import json

# UniDic lex.csv の素性レイアウト (0-indexed)
#  0:surface 1:leftId 2:rightId 3:cost
#  4:pos1 5:pos2 6:pos3 7:pos4 8:cType 9:cForm
# 10:lForm 11:lemma 12:orth 13:pron 14:orthBase 15:pronBase
# 16:goshu 17:iType 18:iForm 19:fType 20:fForm
# 21:iConType 22:fConType 23:type 24:kana 25:kanaBase 26:form 27:formBase ...
COL_SURFACE, COL_COST = 0, 3
COL_P1, COL_P2, COL_P3, COL_P4 = 4, 5, 6, 7
COL_CTYPE, COL_CFORM = 8, 9
COL_LFORM, COL_LEMMA, COL_PRON = 10, 11, 13
COL_GOSHU = 16
COL_KANA = 24
MIN_COLUMNS = 18

# 活用型（cType）に現れる行名 -> Mozc の行名。「ワア行」は「ア行」より先に判定すること。
GYOU_ORDER = ("ワア行", "ワ行", "カ行", "ガ行", "サ行", "タ行",
              "ナ行", "バ行", "マ行", "ラ行", "ハ行", "ア行")
GYOU_TO_MOZC = {
    "ワア行": "ワ行", "ワ行": "ワ行", "ア行": "ワ行",
    "カ行": "カ行", "ガ行": "ガ行", "サ行": "サ行", "タ行": "タ行",
    "ナ行": "ナ行", "バ行": "バ行", "マ行": "マ行", "ラ行": "ラ行",
    "ハ行": "ハ行",
}

class UnidicConverter:
    def __init__(self, output_dir, config_path=None):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # 外部設定の読み込み
        self.pos_rules = []
        self.default_mapping = {}
        # 語種（goshu）によるノイズ判定。UniDic の語種は 和/漢/外/混/固/記号/不明/※。
        # 既定では無効。「記号」には VR・PK・GLP のような英字略語（p1=名詞）が
        # 3,000語以上含まれており、落とすとIMEに有用な語彙を失う。真の記号は
        # is_noise() の p1=補助記号/記号 の判定で既に除外される。
        self.noise_goshu = set()
        if config_path and os.path.exists(config_path) and self.load_config(config_path):
            print(f"[*] Loaded POS mapping config: {config_path}")

        # 全角半角変換テーブルを事前に作成して高速化
        self.trans_table = str.maketrans(
            '！＂＃＄％＆＇（）＊＋，－．／０１２３４５６７８９：；＜＝＞？＠ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ［＼］＾＿｀ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ｛｜｝～',
            '!\"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~'
        )
        # UniDicはCSVなので、クォートされたフィールドにタブや改行が入りうる。
        # そのまま書き出すとTSVの列がずれ、改行の場合は実在しない語が1行生まれる。
        self.trans_table.update({ord('\t'): None, ord('\n'): None, ord('\r'): None})

        # 読みのクレンジング用正規表現を事前にコンパイルして高速化
        self.re_clean_reading = re.compile(r'[^ぁ-ゖー]')

    def fullwidth_to_halfwidth(self, text):
        """英数字と記号の範囲（！〜〜）を半角化し、あわせてTSVを壊す制御文字を除去する。"""
        if not text: return ""
        return text.translate(self.trans_table)

    def katakana_to_hiragana(self, text):
        if not text: return ""
        return "".join(chr(ord(c) - 96) if "ァ" <= c <= "ヶ" else c for c in text)

    def load_config(self, config_path):
        try:
            with open(config_path, 'r', encoding='utf-8-sig') as f:
                config = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[!] Error loading JSON: {e}")
            return False
        self.pos_rules = config.get('pos_rules', [])
        self.default_mapping = config.get('default_mapping', {})
        if 'noise_goshu' in config:
            self.noise_goshu = set(config['noise_goshu'])
        return True

    def _match_condition(self, rule_match, u_data):
        """ルールがUniDicデータに適合するか判定"""
        for key, expected in rule_match.items():
            is_contains = key.endswith('_contains')
            target_key = key[:-len('_contains')] if is_contains else key

            val = u_data.get(target_key, "*")

            if is_contains:
                # リストなら「すべて含む」
                if isinstance(expected, list):
                    if not all(e in val for e in expected): return False
                else:
                    if expected not in val: return False
            else:
                # リストなら「いずれかに一致」
                if isinstance(expected, list):
                    if val not in expected: return False
                else:
                    if val != expected: return False
        return True

    def map_pos_mozc(self, row, surface):
        """外部ルールまたは組込ロジックで品詞をマッピング。
        surface は半角化済みの表記（判定と出力で表記を一致させるため）。

        判定の優先順位は JSON 経路・組込経路で共通:
          1. UniDic が与える具体的な品詞（固有名詞・数詞・用言・接辞・記号 等）
          2. アルファベット（ASCII英字のみの表記）
          3. 名詞などの一般的なフォールバック
        設定が無い場合は組込ロジックが 1〜3 をすべて担うため、そのまま委譲する。"""
        if not self.pos_rules and not self.default_mapping:
            return self.map_pos_mozc_builtin(row, surface)

        u_data = {
            'surface': surface,
            'p1': row[COL_P1],
            'p2': row[COL_P2],
            'p3': row[COL_P3],
            'p4': row[COL_P4] if len(row) > COL_P4 else "*",
            'cType': row[COL_CTYPE] if len(row) > COL_CTYPE else "*",
            'cForm': row[COL_CFORM] if len(row) > COL_CFORM else "*",
        }

        # 1. 外部ルールによる判定
        for rule in self.pos_rules:
            if self._match_condition(rule.get('match', {}), u_data):
                return rule.get('result')

        # 2. アルファベット判定。UniDic が固有名詞・動詞等の具体的な品詞を与えている
        #    場合はそちらを優先し、これは一般名詞などに対するフォールバックとする。
        #    判定は必ず半角化「後」の表記で行う（ＡＰＩ -> API）。
        if surface.isascii() and surface.isalpha():
            return "アルファベット"

        # 3. 単純マッピング（フォールバック）
        if u_data['p1'] in self.default_mapping:
            return self.default_mapping[u_data['p1']]

        # 4. 組込ロジック (JSONがない場合やマッチしない場合)
        return self.map_pos_mozc_builtin(row, surface)

    @staticmethod
    def _gyou_tag(cType, yodan=False):
        """活用型から「動詞〇行五段」等を決定。文語四段のハ行のみ専用タグを返す。"""
        for gyou in GYOU_ORDER:
            if gyou in cType:
                mozc_gyou = GYOU_TO_MOZC[gyou]
                if mozc_gyou == "ハ行":
                    # 文語ハ行四段（思ふ・問ふ）はMozcに専用品詞がある
                    return "動詞ハ行四段" if yodan else "動詞ワ行五段"
                return f"動詞{mozc_gyou}五段"
        return None

    @classmethod
    def map_verb(cls, surface, cType):
        """UniDicの活用型（サ行変格・五段-ワア行・文語四段-ハ行 等）をMozcの動詞品詞へ。"""
        # 変格活用を最優先（「文語サ行変格」等の接頭辞付きも拾う）
        if "カ行変格" in cType: return "動詞カ変"
        if "サ行変格" in cType:
            # 「論ずる」「命ずる」等はMozcではザ変として扱う
            return "動詞ザ変" if surface.endswith(("ずる", "ズル")) else "動詞サ変"
        if "ラ行変格" in cType: return "動詞ラ変"
        if "ナ行変格" in cType: return "動詞ナ行五段"  # 死ぬ・往ぬ

        if "五段" in cType:
            return cls._gyou_tag(cType) or "動詞ワ行五段"
        if "四段" in cType:  # 文語四段
            return cls._gyou_tag(cType, yodan=True) or "動詞ワ行五段"
        if "一段" in cType: return "動詞一段"
        if "二段" in cType: return "動詞一段"  # 文語二段は現代語の一段で近似
        return "動詞一段"

    def map_pos_mozc_builtin(self, row, surface=None):
        """
        UniDicの各カラムからMozcの提供された品詞へ高度に精細マッピング。
        """
        if surface is None:
            surface = self.fullwidth_to_halfwidth(row[COL_SURFACE])
        p1, p2, p3 = row[COL_P1], row[COL_P2], row[COL_P3]
        p4 = row[COL_P4] if len(row) > COL_P4 else "*"
        cType = row[COL_CTYPE] if len(row) > COL_CTYPE else "*"

        # 1. 固有名詞系
        if p2 == "固有名詞":
            if p3 == "人名" or p4 in ["姓", "名"]: return "人名"
            if p3 == "地名" or p4 == "地名": return "地名"
            if "組織" in p3 or "組織" in p4: return "組織"
            return "固有名詞"

        # 2. 数詞・助数詞系
        if p2 == "数詞": return "数"
        if "助数詞" in [p2, p3]: return "助数詞"

        # 3. 用言系 (動詞)
        if p1 == "動詞":
            return self.map_verb(surface, cType)

        if p1 == "形容詞": return "形容詞"

        # 4. 接頭・接尾辞
        if p1 == "接頭辞": return "接頭語"
        if p1 == "接尾辞":
            if p3 == "人名": return "接尾人名"
            if p3 == "地名": return "接尾地名"
            return "接尾一般"

        # 5. 記号・特殊系
        if p1 in ["記号", "補助記号"]:
            if p2 == "顔文字" or "顔文字" in p3: return "顔文字"
            if p2 in ["句点", "読点"]: return "句読点"
            return "記号"

        # 6. アルファベット判定（固有名詞・用言等の具体的な品詞より後段）
        if surface.isascii() and surface.isalpha():
            return "アルファベット"

        # 7. 名詞系
        if p1 == "名詞":
            if "サ変" in p2 or "サ変" in p3: return "名詞サ変"
            return "名詞"

        if p1 == "形状詞":
            # 形状詞（形容動詞）はMozc内部仕様の「名詞形動」へマッピング（活用可能になる）
            return "名詞形動"

        # 8. その他の自立語・付属語
        mapping = {
            "副詞": "副詞",
            "連体詞": "連体詞",
            "接続詞": "接続詞",
            "感動詞": "感動詞",
            "助詞": "独立語",
            "助動詞": "独立語",
            "代名詞": "名詞"
        }
        return mapping.get(p1, "名詞")

    def is_noise(self, row):
        """
        実用性の低いエントリを排除する。
        """
        surface = row[COL_SURFACE]
        p1 = row[COL_P1]
        cForm = row[COL_CFORM]      # 活用形
        goshu = row[COL_GOSHU]      # 語種（和/漢/外/混/固/記号/不明）

        # 1. 活用語は「基本形（終止形）」以外すべてカット
        if cForm != "" and "*" not in cForm:
            if "終止形-一般" not in cForm and "基本形" not in cForm:
                return True

        # 2. 語種によるフィルタ
        if goshu in self.noise_goshu:
            return True

        # 3. 特殊なID系エントリ
        if surface.startswith(("＠", "@")) or surface.isdigit():
            return True

        # 4. 極端に短い、または記号混じりのノイズ
        if len(surface) == 0: return True
        if p1 in ["補助記号", "記号"]: return True

        return False

    def convert(self, csv_path: str, output_name: str) -> None:
        output_file = os.path.join(self.output_dir, output_name)
        if os.path.exists(output_file):
            print(f"[!] Warning: overwriting existing file: {output_file}")
        print(f"\n[Process] Processing: {csv_path}")

        unique_entries = set()  # 重複排除: (reading, surface, pos)
        stats = {"processed": 0, "written": 0}

        try:
            # BOM付きで配布される版があるため utf-8-sig で開く
            with open(csv_path, "r", encoding="utf-8-sig", newline='') as f_in, \
                 open(output_file, "w", encoding="utf-8", newline='') as f_out:
                reader = csv.reader(f_in)
                for row in reader:
                    stats["processed"] += 1
                    if stats["processed"] % 100000 == 0:
                        print(f"\r  Scanned {stats['processed']}... Saved {stats['written']}", end="", flush=True)

                    if len(row) < MIN_COLUMNS: continue

                    # ノイズ判定
                    if self.is_noise(row): continue

                    surface = self.fullwidth_to_halfwidth(row[COL_SURFACE])
                    if not surface: continue  # 制御文字のみだった等

                    # IME入力に最適な「仮名形出現形（row[24]）」を最優先。長音記号化を防ぎつつ、砕けた発音もカバー
                    reading_katakana = row[COL_KANA] if (len(row) > COL_KANA and row[COL_KANA] != "*") else ""
                    if not reading_katakana:
                        # フォールバック1: 語彙素読み（標準読み）
                        reading_katakana = row[COL_LFORM] if row[COL_LFORM] != "*" else ""
                    if not reading_katakana:
                        # フォールバック2: 発音形出現形（実際の発音）
                        reading_katakana = row[COL_PRON] if row[COL_PRON] != "*" else ""

                    if not reading_katakana: continue

                    reading = self.katakana_to_hiragana(reading_katakana)
                    reading = self.re_clean_reading.sub('', reading)
                    if not reading: continue

                    # 読みと表記が同じ（ひらがなのみ）はスキップ
                    if reading == surface: continue

                    # 平仮名1文字 -> アルファベット1文字の単純マッピングを排除 (あ->A等)
                    if len(reading) == 1 and len(surface) == 1 and surface.isascii() and surface.isalpha():
                        continue

                    # 品詞マッピング
                    pos = self.map_pos_mozc(row, surface)

                    # 重複チェック
                    entry_key = (reading, surface, pos)
                    if entry_key in unique_entries: continue

                    # コメント作成 (語種 + 語彙素)
                    goshu = row[COL_GOSHU]
                    lemma = row[COL_LEMMA]
                    cost = row[COL_COST]  # 単語生起コスト (出現しやすさのスコア)
                    comment = self.fullwidth_to_halfwidth(f"UniDic [{goshu}] / {lemma}")

                    # コスト（頻度順位）を第5カラムとして出力
                    f_out.write(f"{reading}\t{surface}\t{pos}\t{comment}\t{cost}\n")
                    unique_entries.add(entry_key)
                    stats["written"] += 1

        except (OSError, csv.Error, UnicodeDecodeError) as e:
            print(f"\nError processing {csv_path}: {e}")
            raise SystemExit(1)

        print(f"\nFinished. Scanned: {stats['processed']}, Unique Practical Words: {stats['written']}")
        print(f"Result saved to: {output_file}")


def default_output_name(csv_path):
    """親ディレクトリ名から出力名を導出（例: unidic-cwj-3.1.0/lex.csv -> mozc_unidic-cwj-3.1.0.tsv）"""
    base = os.path.basename(os.path.dirname(os.path.abspath(csv_path))) or "unidic"
    return f"mozc_{base}.tsv"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="UniDic lex.csv を Mozc ユーザー辞書向けの中間TSVへ変換します。")
    parser.add_argument("lex_csv", help="UniDic の lex.csv へのパス")
    parser.add_argument("output_dir", help="中間TSVの出力先ディレクトリ")
    parser.add_argument("config", nargs="?", default=None,
                        help="品詞マッピングJSON（省略時は config/pos_mapping.json）")
    parser.add_argument("-o", "--name", default=None,
                        help="出力ファイル名。省略時は親ディレクトリ名から導出（上書き事故の回避に推奨）")
    args = parser.parse_args(argv)

    config_path = args.config
    if config_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        config_path = os.path.join(project_root, "config", "pos_mapping.json")

    if not os.path.exists(config_path):
        print(f"[!] Config not found, falling back to built-in rules: {config_path}")
        config_path = None

    if not os.path.exists(args.lex_csv):
        print(f"Error: input not found: {args.lex_csv}")
        return 1

    converter = UnidicConverter(args.output_dir, config_path)
    converter.convert(args.lex_csv, args.name or default_output_name(args.lex_csv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
