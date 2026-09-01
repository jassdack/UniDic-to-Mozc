"""convert_unidic.py / merge_unidics.py の回帰テスト（標準ライブラリのみ）。

実行: python -m unittest discover -s tests
"""
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "converter_scripts"))

import convert_unidic  # noqa: E402
import merge_unidics   # noqa: E402

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "pos_mapping.json")


def lex_row(surface, cost=5000, p1="名詞", p2="普通名詞", p3="一般", p4="*",
            cType="*", cForm="*", lForm="*", lemma=None, pron="*",
            goshu="和", kana="*"):
    """UniDic lex.csv の 1 行を標準レイアウトで組み立てる。"""
    r = ["*"] * 30
    r[convert_unidic.COL_SURFACE] = surface
    r[1] = r[2] = "1"
    r[convert_unidic.COL_COST] = str(cost)
    r[convert_unidic.COL_P1] = p1
    r[convert_unidic.COL_P2] = p2
    r[convert_unidic.COL_P3] = p3
    r[convert_unidic.COL_P4] = p4
    r[convert_unidic.COL_CTYPE] = cType
    r[convert_unidic.COL_CFORM] = cForm
    r[convert_unidic.COL_LFORM] = lForm
    r[convert_unidic.COL_LEMMA] = lemma if lemma is not None else surface
    r[convert_unidic.COL_PRON] = pron
    r[convert_unidic.COL_GOSHU] = goshu
    r[17] = "*"  # iType — 語種と間違えやすい隣接カラム
    r[convert_unidic.COL_KANA] = kana
    return r


def run_convert(rows, tmpdir, config_path=CONFIG_PATH, name="out.tsv"):
    """rows を lex.csv に書き出して変換し、TSV の各行をタプルで返す。"""
    lex = os.path.join(tmpdir, "lex.csv")
    with open(lex, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    with redirect_stdout(io.StringIO()):
        conv = convert_unidic.UnidicConverter(tmpdir, config_path)
        conv.convert(lex, name)
    with open(os.path.join(tmpdir, name), encoding="utf-8") as f:
        return [tuple(line.rstrip("\n").split("\t")) for line in f]


class VerbConjugationTest(unittest.TestCase):
    """UniDic の活用型は「サ行変格」であって IPAdic の「サ変」ではない。"""

    CASES = [
        # (表層形, cType, 期待するMozc品詞, 仮名形)
        ("勉強する", "サ行変格", "動詞サ変", "ベンキョウスル"),
        ("察する", "サ行変格", "動詞サ変", "サッスル"),
        ("論ずる", "サ行変格", "動詞ザ変", "ロンズル"),
        ("来る", "カ行変格", "動詞カ変", "クル"),
        ("有り", "文語ラ行変格", "動詞ラ変", "アリ"),
        ("死ぬ", "五段-ナ行", "動詞ナ行五段", "シヌ"),
        ("買う", "五段-ワア行", "動詞ワ行五段", "カウ"),
        ("書く", "五段-カ行", "動詞カ行五段", "カク"),
        ("泳ぐ", "五段-ガ行", "動詞ガ行五段", "オヨグ"),
        ("話す", "五段-サ行", "動詞サ行五段", "ハナス"),
        ("待つ", "五段-タ行", "動詞タ行五段", "マツ"),
        ("遊ぶ", "五段-バ行", "動詞バ行五段", "アソブ"),
        ("読む", "五段-マ行", "動詞マ行五段", "ヨム"),
        ("走る", "五段-ラ行", "動詞ラ行五段", "ハシル"),
        ("見る", "上一段-マ行", "動詞一段", "ミル"),
        ("食べる", "下一段-バ行", "動詞一段", "タベル"),
        ("思ふ", "文語四段-ハ行", "動詞ハ行四段", "オモウ"),
        ("受く", "文語下二段-カ行", "動詞一段", "ウク"),
    ]

    def test_via_json_rules(self):
        rows = [lex_row(s, p1="動詞", p2="一般", cType=c, cForm="終止形-一般", kana=k)
                for s, c, _, k in self.CASES]
        with tempfile.TemporaryDirectory() as d:
            got = {r[1]: r[2] for r in run_convert(rows, d)}
        for surface, _, expected, _k in self.CASES:
            with self.subTest(surface=surface):
                self.assertEqual(got.get(surface), expected)

    def test_via_builtin_rules(self):
        """JSON を読まない組込ロジック側も同じ結論を出すこと。"""
        for surface, cType, expected, _k in self.CASES:
            with self.subTest(surface=surface):
                self.assertEqual(
                    convert_unidic.UnidicConverter.map_verb(surface, cType), expected)

    def test_json_and_builtin_agree(self):
        rows = [lex_row(s, p1="動詞", p2="一般", cType=c, cForm="終止形-一般", kana=k)
                for s, c, _, k in self.CASES]
        with tempfile.TemporaryDirectory() as d:
            with_json = run_convert(rows, d, CONFIG_PATH, "a.tsv")
            without = run_convert(rows, d, None, "b.tsv")
        self.assertEqual(with_json, without)


class GoshuColumnTest(unittest.TestCase):
    """語種は row[16]。row[17] は語頭変化型(iType)で、参照するとフィルタが無効化される。"""

    def test_goshu_index_is_16(self):
        self.assertEqual(convert_unidic.COL_GOSHU, 16)

    def test_symbol_goshu_is_dropped(self):
        rows = [
            lex_row("〄", goshu="記号", kana="キゴウ"),
            lex_row("星", goshu="和", kana="ホシ"),
        ]
        with tempfile.TemporaryDirectory() as d:
            got = [r[1] for r in run_convert(rows, d)]
        self.assertEqual(got, ["星"])

    def test_comment_carries_real_goshu(self):
        rows = [lex_row("珈琲", goshu="外", kana="コーヒー")]
        with tempfile.TemporaryDirectory() as d:
            got = run_convert(rows, d)
        self.assertEqual(got[0][3], "UniDic [外] / 珈琲")


class SurfaceNormalizationTest(unittest.TestCase):
    def test_fullwidth_alpha_is_classified_as_alphabet(self):
        """表記を半角化するなら、品詞判定も半角化後の表記で行うこと。"""
        rows = [lex_row("ＡＰＩ", p2="普通名詞", kana="エーピーアイ")]
        with tempfile.TemporaryDirectory() as d:
            got = run_convert(rows, d)
        self.assertEqual(got[0][1], "API")
        self.assertEqual(got[0][2], "アルファベット")

    def test_reading_is_hiragana_only(self):
        rows = [lex_row("珈琲", kana="コーヒー")]
        with tempfile.TemporaryDirectory() as d:
            got = run_convert(rows, d)
        self.assertEqual(got[0][0], "こーひー")


class PosPriorityTest(unittest.TestCase):
    """1. UniDicの具体的な品詞 > 2. アルファベット > 3. 一般フォールバック
    の優先順位が JSON 経路・組込経路の双方で保たれること。"""

    CASES = [
        ("Google", "固有名詞", dict(p2="固有名詞"), "グーグル"),
        ("Tokyo", "地名", dict(p2="固有名詞", p3="地名"), "トウキョウ"),
        ("Smith", "人名", dict(p2="固有名詞", p3="人名"), "スミス"),
        ("ＡＰＩ", "アルファベット", {}, "エーピーアイ"),   # 半角化後の表記で判定される
        ("IT", "アルファベット", {}, "アイティー"),
        ("星", "名詞", {}, "ホシ"),
        ("勉強", "名詞サ変", dict(p3="サ変可能"), "ベンキョウ"),
    ]
    EXPECTED = {"Google": "固有名詞", "Tokyo": "地名", "Smith": "人名",
                "API": "アルファベット", "IT": "アルファベット",
                "星": "名詞", "勉強": "名詞サ変"}

    def _classify(self, config_path):
        rows = [lex_row(s, kana=k, **kw) for s, _, kw, k in self.CASES]
        with tempfile.TemporaryDirectory() as d:
            return {r[1]: r[2] for r in run_convert(rows, d, config_path)}

    def test_json_path(self):
        self.assertEqual(self._classify(CONFIG_PATH), self.EXPECTED)

    def test_builtin_path_matches_json_path(self):
        """設定なしでも同じ結論になること（アルファベット判定が固有名詞を潰さない）。"""
        self.assertEqual(self._classify(CONFIG_PATH), self._classify(None))


class NoiseFilterTest(unittest.TestCase):
    def test_non_terminal_forms_are_dropped(self):
        rows = [
            lex_row("書く", p1="動詞", cType="五段-カ行", cForm="終止形-一般", kana="カク"),
            lex_row("書か", p1="動詞", cType="五段-カ行", cForm="未然形-一般", kana="カカ"),
            lex_row("書い", p1="動詞", cType="五段-カ行", cForm="連用形-イ音便", kana="カイ"),
        ]
        with tempfile.TemporaryDirectory() as d:
            got = [r[1] for r in run_convert(rows, d)]
        self.assertEqual(got, ["書く"])

    def test_short_rows_and_id_entries_are_dropped(self):
        rows = [
            lex_row("＠１２３", kana="アットマーク"),
            lex_row("12345", kana="イチニサンヨンゴ"),
            lex_row("星", kana="ホシ"),
        ]
        with tempfile.TemporaryDirectory() as d:
            got = [r[1] for r in run_convert(rows, d)]
        self.assertEqual(got, ["星"])


class TsvIntegrityTest(unittest.TestCase):
    """UniDicはCSVなので、クォート内のタブ・改行がTSVの列を壊しうる。"""

    def test_control_chars_never_break_columns(self):
        rows = [
            lex_row("タブ\t入り", kana="タブイリ"),
            lex_row("普通", lemma="改行\n入り", kana="フツウ"),
            lex_row("星", kana="ホシ"),
        ]
        with tempfile.TemporaryDirectory() as d:
            lines = run_convert(rows, d)
        self.assertEqual(len(lines), 3, "改行が幻のエントリを生んでいる")
        for cols in lines:
            self.assertEqual(len(cols), 5, f"列数が壊れている: {cols}")
        self.assertEqual(lines[0][1], "タブ入り")
        self.assertEqual(lines[1][3], "UniDic [和] / 改行入り")

    def test_reading_is_cleansed_to_hiragana_and_choon(self):
        rows = [
            lex_row("珈琲", kana="コーヒー"),
            lex_row("ヴァイオリン属", kana="ヴァイオリン"),
            lex_row("一ヶ月", kana="イッカゲツ"),
            lex_row("パソコン部", kana="パソコン・ブ"),
        ]
        with tempfile.TemporaryDirectory() as d:
            got = [r[0] for r in run_convert(rows, d)]
        self.assertEqual(got, ["こーひー", "ゔぁいおりん", "いっかげつ", "ぱそこんぶ"])

    def test_entry_without_usable_reading_is_dropped(self):
        rows = [lex_row("記号語", kana="＊＊＊", lForm="*", pron="*"),
                lex_row("星", kana="ホシ")]
        with tempfile.TemporaryDirectory() as d:
            got = [r[1] for r in run_convert(rows, d)]
        self.assertEqual(got, ["星"])


class MergeTest(unittest.TestCase):
    def _write(self, path, lines):
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(l + "\n" for l in lines)

    def test_creates_missing_output_directory(self):
        """README の例は存在しない output/ を指す。落ちてはならない。"""
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.tsv")
            self._write(a, ["ほし\t星\t名詞\tUniDic [和] / 星\t4000"])
            out = os.path.join(d, "does", "not", "exist", "m.tsv")
            with redirect_stdout(io.StringIO()):
                rc = merge_unidics.merge_unidics([a], out)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "does", "not", "exist", "m_1.tsv")))

    def test_missing_inputs_fail_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                rc = merge_unidics.merge_unidics(
                    [os.path.join(d, "nope.tsv")], os.path.join(d, "m.tsv"))
            self.assertEqual(rc, 1)

    def test_comment_is_preserved_and_cost_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.tsv")
            self._write(a, ["ほし\t星\t名詞\tUniDic [和] / 星\t4000"])
            out = os.path.join(d, "m.tsv")
            with redirect_stdout(io.StringIO()):
                merge_unidics.merge_unidics([a], out)
            with open(os.path.join(d, "m_1.tsv"), encoding="utf-8") as f:
                cols = f.readline().rstrip("\n").split("\t")
        self.assertEqual(cols, ["ほし", "星", "名詞", "UniDic [和] / 星"])

    def test_lower_cost_wins_and_sorted_by_reading_then_cost(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.tsv"), os.path.join(d, "b.tsv")
            self._write(a, [
                "こう\t光\t名詞\tA\t9000",
                "こう\t甲\t名詞\tB\t100",
            ])
            self._write(b, ["こう\t光\t名詞\tC\t50"])
            out = os.path.join(d, "m.tsv")
            with redirect_stdout(io.StringIO()):
                merge_unidics.merge_unidics([a, b], out)
            with open(os.path.join(d, "m_1.tsv"), encoding="utf-8") as f:
                rows = [l.rstrip("\n").split("\t") for l in f]
        self.assertEqual([r[1] for r in rows], ["光", "甲"])   # cost 50 < 100
        self.assertEqual(rows[0][3], "C")                      # 低コスト側のコメントを採用

    def test_accepts_more_than_two_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i, (r, s) in enumerate([("あ", "亜"), ("い", "威"), ("う", "宇")]):
                p = os.path.join(d, f"{i}.tsv")
                self._write(p, [f"{r}\t{s}\t名詞\tX\t{1000 + i}"])
                paths.append(p)
            out = os.path.join(d, "m.tsv")
            with redirect_stdout(io.StringIO()):
                rc = merge_unidics.merge_unidics(paths, out)
            with open(os.path.join(d, "m_1.tsv"), encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 3)
        self.assertEqual(rc, 0)

    def test_splits_at_the_100k_limit(self):
        original, merge_unidics.LIMIT = merge_unidics.LIMIT, 2
        try:
            with tempfile.TemporaryDirectory() as d:
                a = os.path.join(d, "a.tsv")
                self._write(a, [f"よみ{i}\t語{i}\t名詞\tX\t{i}" for i in range(5)])
                out = os.path.join(d, "m.tsv")
                with redirect_stdout(io.StringIO()):
                    merge_unidics.merge_unidics([a], out)
                produced = sorted(p for p in os.listdir(d) if p.startswith("m_"))
            self.assertEqual(produced, ["m_1.tsv", "m_2.tsv", "m_3.tsv"])
        finally:
            merge_unidics.LIMIT = original


class ConfigTest(unittest.TestCase):
    def test_shipped_config_only_emits_documented_pos(self):
        """result の文字列が config/mozc_pos_list.md の見出しと一致していること。"""
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        doc = os.path.join(PROJECT_ROOT, "config", "mozc_pos_list.md")
        with open(doc, encoding="utf-8") as f:
            text = f.read()
        import re
        # 見出し（箇条書き / 表の1列目）の先頭に置かれた品詞名のみを拾う
        known = set(re.findall(r"^(?:- |\| )`([^`]+)`", text, re.MULTILINE))
        self.assertGreater(len(known), 40, "品詞一覧の抽出に失敗している")
        results = {r["result"] for r in config["pos_rules"]}
        results |= set(config["default_mapping"].values())
        self.assertEqual(results - known, set())


if __name__ == "__main__":
    unittest.main()
