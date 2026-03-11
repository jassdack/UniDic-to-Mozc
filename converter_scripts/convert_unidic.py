import os
import csv
import re
import sys
import json

class UnidicConverter:
    def __init__(self, output_dir, config_path=None):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 外部設定の読み込み
        self.pos_rules = []
        self.default_mapping = {}
        if config_path and os.path.exists(config_path):
            self.load_config(config_path)
            print(f"[*] Loaded POS mapping config: {config_path}")
        
        # 改善点1: 全角半角変換テーブルを事前に作成して高速化
        self.trans_table = str.maketrans(
            '！＂＃＄％＆＇（）＊＋，－．／０１２３４５６７８９：；＜＝＞？＠ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ［＼］＾＿｀ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ｛｜｝～',
            '!\"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~'
        )
        
        # 改善点2: 読みのクレンジング用正規表現を事前に準備（コンパイル）して高速化
        self.re_clean_reading = re.compile(r'[^\u3041-\u3096\u30FC]')

    def fullwidth_to_halfwidth(self, text):
        if not text: return ""
        # 英数字と記号の範囲（！〜〜）を半角に変換
        return text.translate(self.trans_table)

    def katakana_to_hiragana(self, text):
        if not text: return ""
        return "".join(chr(ord(c) - 96) if "\u30a1" <= c <= "\u30f6" else c for c in text)

    def load_config(self, config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.pos_rules = config.get('pos_rules', [])
                self.default_mapping = config.get('default_mapping', {})
        except Exception as e:
            print(f"[!] Error loading JSON: {e}")

    def _match_condition(self, rule_match, u_data):
        """ルールがUniDicデータに適合するか判定"""
        for key, expected in rule_match.items():
            is_contains = False
            target_key = key
            if key.endswith('_contains'):
                is_contains = True
                target_key = key.replace('_contains', '')
            
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

    def map_pos_mozc(self, row):
        """外部ルールまたは組込ロジックで品詞をマッピング"""
        surface = row[0]
        u_data = {
            'surface': surface,
            'p1': row[4],
            'p2': row[5],
            'p3': row[6],
            'p4': row[7] if len(row) > 7 else "*",
            'cType': row[8] if len(row) > 8 else "*",
            'cForm': row[9] if len(row) > 9 else "*"
        }

        # 1. 外部ルールによる判定
        for rule in self.pos_rules:
            if self._match_condition(rule.get('match', {}), u_data):
                return rule.get('result')

        # 2. 特殊な自動判定
        if surface.isascii() and surface.isalpha():
            return "アルファベット"

        # 3. 単純マッピング（フォールバック）
        if u_data['p1'] in self.default_mapping:
            return self.default_mapping[u_data['p1']]

        # 4. 組込ロジック (YAMLがない場合やマッチしない場合)
        return self.map_pos_mozc_builtin(row)

    def map_pos_mozc_builtin(self, row):
        """
        UniDicの各カラムからMozcの提供された品詞へ高度に精細マッピング。
        row: [0:surface, 4:p1, 5:p2, 6:p3, 7:p4, 8:cType, 9:cForm, ...]
        """
        surface = row[0]
        p1, p2, p3 = row[4], row[5], row[6]
        p4 = row[7] if len(row) > 7 else "*"
        cType = row[8] if len(row) > 8 else "*"
        
        # 1. アルファベット判定
        if surface.isascii() and surface.isalpha():
            return "アルファベット"

        # 2. 固有名詞系
        if p2 == "固有名詞":
            if p3 == "人名" or p4 in ["姓", "名"]: return "人名"
            if p3 == "地名" or p4 == "地名": return "地名"
            if "組織" in p3 or "組織" in p4: return "組織"
            return "固有名詞"
            
        # 3. 数詞・助数詞系
        if p2 == "数詞": return "数"
        if "助数詞" in [p2, p3]: return "助数詞"
        
        # 4. 用言系 (動詞)
        if p1 == "動詞":
            if "五段" in cType:
                if "カ行" in cType: return "動詞カ行五段"
                if "ガ行" in cType: return "動詞ガ行五段"
                if "サ行" in cType: return "動詞サ行五段"
                if "タ行" in cType: return "動詞タ行五段"
                if "ナ行" in cType: return "動詞ナ行五段"
                if "バ行" in cType: return "動詞バ行五段"
                if "マ行" in cType: return "動詞マ行五段"
                if "ラ行" in cType: return "動詞ラ行五段"
                if "ワ行" in cType: return "動詞ワ行五段"
                return "動詞ワ行五段" # fallback
            if "一段" in cType: return "動詞一段"
            if "サ変" in cType: return "動詞サ変"
            if "カ変" in cType: return "動詞カ変"
            if "ザ変" in cType: return "動詞ザ変"
            if "ラ変" in cType: return "動詞ラ変"
            return "動詞一段" # fallback

        if p1 == "形容詞": return "形容詞"
        
        # 5. 接頭・接尾辞
        if p1 == "接頭辞": return "接頭語"
        if p1 == "接尾辞":
            if p3 == "人名": return "接尾人名"
            if p3 == "地名": return "接尾地名"
            return "接尾一般"
            
        # 6. 記号・特殊系
        if p1 in ["記号", "補助記号"]:
            if p2 == "顔文字" or "顔文字" in p3: return "顔文字"
            if p2 in ["句点", "読点"]: return "句読点"
            return "記号"
            
        # 7. 名詞系
        if p1 == "名詞":
            if "サ変" in p2 or "サ変" in p3: return "名詞サ変"
            if p2 == "普通名詞": return "名詞"
            if p2 == "代名詞": return "名詞"
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
        surface = row[0]
        p1 = row[4] # p2, p3は未使用だったため省略
        cForm = row[9] # 活用形
        goshu = row[17] if len(row) > 17 else ""
        
        # 1. 活用語は「基本形（終止形）」以外すべてカット
        if cForm != "" and "*" not in cForm:
            if "終止形-一般" not in cForm and "基本形" not in cForm:
                return True
        
        # 2. 語種によるフィルタ
        if goshu in ["記号", "不可触", "他"]:
            return True
            
        # 3. 特殊なID系エントリ
        # 改善点3: startswithの複数指定と、isdigit()によるシンプルな数字判定
        if surface.startswith(("＠", "@")) or surface.isdigit():
            return True

        # 4. 極端に短い、または記号混じりのノイズ
        if len(surface) == 0: return True
        if p1 in ["補助記号", "記号"]: return True
        
        return False

    def convert(self, csv_path, output_name):
        output_file = os.path.join(self.output_dir, output_name)
        print(f"\n[Process] Processing: {csv_path}")
        
        processed = 0
        written = 0
        unique_entries = set() # 重複排除: (reading, surface, pos)
        
        try:
            # 改善点4: newline='' を追加して安全にファイルを開く
            with open(csv_path, "r", encoding="utf-8", newline='') as f_in, \
                 open(output_file, "w", encoding="utf-8", newline='') as f_out:
                
                reader = csv.reader(f_in)
                for row in reader:
                    processed += 1
                    if processed % 100000 == 0:
                        print(f"\r  Scanned {processed}... Saved {written}", end="", flush=True)
                    
                    if len(row) < 18: continue
                    
                    # ノイズ判定
                    if self.is_noise(row): continue
                    
                    surface = self.fullwidth_to_halfwidth(row[0])
                    # IME入力に最適な「仮名形出現形（row[24]）」を最優先。長音記号化を防ぎつつ、砕けた発音もカバー
                    reading_katakana = row[24] if (len(row) > 24 and row[24] != "*") else ""
                    if not reading_katakana:
                        # フォールバック1: 語彙素読み（標準読み）
                        reading_katakana = row[10] if (len(row) > 10 and row[10] != "*") else ""
                    if not reading_katakana:
                        # フォールバック2: 語形読み（実際の発音）
                        reading_katakana = row[13] if (len(row) > 13 and row[13] != "*") else ""
                    
                    if not reading_katakana: continue
                    
                    reading = self.katakana_to_hiragana(reading_katakana)
                    
                    # 改善点2: 事前準備した正規表現を使ってクレンジング
                    reading = self.re_clean_reading.sub('', reading)
                    if not reading: continue
                    
                    # 読みと表記が同じ（ひらがなのみ）はスキップ
                    if reading == surface: continue
                    
                    # 改善点5: 平仮名1文字 -> アルファベット1文字の単純マッピングを排除 (あ->A等)
                    if len(reading) == 1 and len(surface) == 1 and surface.isascii() and surface.isalpha():
                        continue
                    
                    # 品詞マッピング
                    pos = self.map_pos_mozc(row)
                    
                    # 重複チェック
                    entry_key = (reading, surface, pos)
                    if entry_key in unique_entries: continue
                    
                    # コメント作成 (語種 + 語彙素)
                    goshu = row[17] # len(row) < 18 は上で弾いているため安全
                    lemma = self.fullwidth_to_halfwidth(row[11]) # 語彙素
                    cost = row[3] # 単語生起コスト (出現しやすさのスコア)
                    comment = f"UniDic [{goshu}] / {lemma}"
                    
                    # コスト（頻度順位）を第5カラムとして出力
                    f_out.write(f"{reading}\t{surface}\t{pos}\t{comment}\t{cost}\n")
                    unique_entries.add(entry_key)
                    written += 1
                    
        except Exception as e:
            print(f"\nError processing {csv_path}: {e}")
            return

        print(f"\nFinished. Scanned: {processed}, Unique Practical Words: {written}")
        print(f"Result saved to: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python convert_unidic.py <lex_csv_path> <output_dir> [config_path]")
    else:
        csv_path = sys.argv[1]
        output_dir = sys.argv[2]
        
        # デフォルトの設定ファイルパスを自己位置から解決
        if len(sys.argv) > 3:
            config_path = sys.argv[3]
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            config_path = os.path.join(project_root, "config", "pos_mapping.json")

        if not os.path.exists(config_path):
            config_path = None

        converter = UnidicConverter(output_dir, config_path)
        base = os.path.basename(os.path.dirname(csv_path)) or "unidic"
        converter.convert(csv_path, f"mozc_{base}.tsv")
