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
        ("アンズル", "サ行変格", "動詞ザ変", "アンズル"),
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

    def test_alphabet_acronyms_survive_by_default(self):
        """UniDic は VR・PK 等の英字略語の語種を「記号」とする。既定では落とさない。"""
        rows = [
            lex_row("VR", goshu="記号", kana="ブイアール"),
            lex_row("ジーエス", goshu="記号", kana="ジーエス"),
            lex_row("★", p1="補助記号", goshu="記号", kana="ホシジルシ"),
        ]
        with tempfile.TemporaryDirectory() as d:
            got = [r[1] for r in run_convert(rows, d)]
        self.assertEqual(got, ["VR", "ジーエス"], "英字略語まで落ちている")

    def test_noise_goshu_can_be_enabled_via_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "c.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"noise_goshu": ["記号"], "pos_rules": [],
                           "default_mapping": {"名詞": "名詞"}}, f)
            rows = [lex_row("VR", goshu="記号", kana="ブイアール"),
                    lex_row("星", goshu="和", kana="ホシ")]
            got = [r[1] for r in run_convert(rows, d, cfg)]
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


class MergeCliTest(unittest.TestCase):
    """--no-comment を位置引数のどこに置いても動くこと。"""

    def _run(self, argv, d):
        a = os.path.join(d, "a.tsv")
        with open(a, "w", encoding="utf-8") as f:
            f.write("ほし\t星\t名詞\tUniDic [和] / 星\t4000\n")
        out = os.path.join(d, "m.tsv")
        with redirect_stdout(io.StringIO()):
            rc = merge_unidics.main([x.format(a=a, out=out) for x in argv])
        self.assertEqual(rc, 0)
        with open(os.path.join(d, "m_1.tsv"), encoding="utf-8") as f:
            return f.readline().rstrip("\n").split("\t")

    def test_flag_before_positionals(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["--no-comment", "{a}", "{out}"], d)[3], "")

    def test_flag_between_positionals(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["{a}", "--no-comment", "{out}"], d)[3], "")

    def test_flag_after_positionals(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["{a}", "{out}", "--no-comment"], d)[3], "")

    def test_comment_kept_without_flag(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["{a}", "{out}"], d)[3], "UniDic [和] / 星")

    def test_unknown_flag_is_rejected(self):
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()):
                merge_unidics.main(["--no-coment", "a.tsv", "out.tsv"])

    def test_too_few_paths_is_an_error(self):
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()):
                merge_unidics.main(["only-one.tsv"])


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


class MergePosFilterTest(unittest.TestCase):
    """--exclude-pos / --only-pos。既定配布は人名を除外する（eval/ の測定結果に基づく）。"""

    ROWS = [
        "ほし\t星\t名詞\tA\t4000",
        "たなか\t田中\t人名\tB\t3000",
        "たなか\t田中\t地名\tC\t3500",
        "おおさか\t大阪\t地名\tD\t2000",
    ]

    def _merge(self, d, **kw):
        a = os.path.join(d, "a.tsv")
        with open(a, "w", encoding="utf-8") as f:
            f.writelines(l + "\n" for l in self.ROWS)
        out = os.path.join(d, "m.tsv")
        with redirect_stdout(io.StringIO()):
            rc = merge_unidics.merge_unidics([a], out, **kw)
        self.assertEqual(rc, 0)
        with open(os.path.join(d, "m_1.tsv"), encoding="utf-8") as f:
            return [l.rstrip("\n").split("\t") for l in f]

    def test_no_filter_keeps_everything(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(len(self._merge(d)), 4)

    def test_exclude_pos_drops_only_that_pos(self):
        with tempfile.TemporaryDirectory() as d:
            rows = self._merge(d, exclude_pos=["人名"])
        self.assertEqual(len(rows), 3)
        self.assertNotIn("人名", [r[2] for r in rows])

    def test_excluding_names_keeps_surface_supplied_by_another_pos(self):
        """田中は地名としても収録されている。人名を落としても表記自体は残る。"""
        with tempfile.TemporaryDirectory() as d:
            rows = self._merge(d, exclude_pos=["人名"])
        self.assertIn("田中", [r[1] for r in rows])

    def test_only_pos_keeps_just_that_pos(self):
        with tempfile.TemporaryDirectory() as d:
            rows = self._merge(d, only_pos=["人名"])
        self.assertEqual([(r[1], r[2]) for r in rows], [("田中", "人名")])

    def test_multiple_pos_are_comma_separated(self):
        with tempfile.TemporaryDirectory() as d:
            rows = self._merge(d, exclude_pos=["人名", "地名"])
        self.assertEqual([r[1] for r in rows], ["星"])

    def test_exclude_and_only_conflict(self):
        with self.assertRaises(ValueError):
            merge_unidics.build_pos_filter(["人名"], ["地名"])

    def test_filtering_everything_out_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.tsv")
            with open(a, "w", encoding="utf-8") as f:
                f.write("ほし\t星\t名詞\tA\t4000\n")
            with redirect_stdout(io.StringIO()):
                rc = merge_unidics.merge_unidics([a], os.path.join(d, "m.tsv"),
                                                 exclude_pos=["名詞"])
        self.assertEqual(rc, 1)

    def test_misspelled_pos_is_warned_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.tsv")
            with open(a, "w", encoding="utf-8") as f:
                f.write("ほし\t星\t名詞\tA\t4000\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                merge_unidics.merge_unidics([a], os.path.join(d, "m.tsv"),
                                            exclude_pos=["人明"])
        self.assertIn("人明", buf.getvalue())


class MergePosFilterCliTest(unittest.TestCase):
    """値を取るオプションでも、位置引数のどこに置いても動くこと。"""

    def _run(self, argv, d):
        a = os.path.join(d, "a.tsv")
        with open(a, "w", encoding="utf-8") as f:
            f.write("ほし\t星\t名詞\tA\t4000\n")
            f.write("たなか\t田中\t人名\tB\t3000\n")
        out = os.path.join(d, "m.tsv")
        with redirect_stdout(io.StringIO()):
            rc = merge_unidics.main([x.format(a=a, out=out) for x in argv])
        self.assertEqual(rc, 0)
        with open(os.path.join(d, "m_1.tsv"), encoding="utf-8") as f:
            return [l.rstrip("\n").split("\t")[1] for l in f]

    def test_flag_before_positionals(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["--exclude-pos", "人名", "{a}", "{out}"], d), ["星"])

    def test_flag_between_positionals(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["{a}", "--exclude-pos", "人名", "{out}"], d), ["星"])

    def test_flag_after_positionals(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["{a}", "{out}", "--exclude-pos", "人名"], d), ["星"])

    def test_equals_form_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["{a}", "{out}", "--exclude-pos=人名"], d), ["星"])

    def test_only_pos_via_cli(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._run(["--only-pos", "人名", "{a}", "{out}"], d), ["田中"])

    def test_combined_with_no_comment(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                self._run(["{a}", "--exclude-pos", "人名", "--no-comment", "{out}"], d),
                ["星"])

    def test_exclude_and_only_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            with redirect_stdout(io.StringIO()):
                merge_unidics.main(["--exclude-pos", "人名", "--only-pos", "地名",
                                    "a.tsv", "out.tsv"])


class PosPathAgreementTest(unittest.TestCase):
    """JSON経路と組込経路の乖離に対する回帰テスト。

    eval/check_pos_agreement.py で lex.csv 全体を突き合わせた際に見つかった
    4パターンを固定する。合成データは実データの組み合わせを網羅できないため、
    リリース前には同スクリプトで lex.csv 全体も確認すること。
    """

    # (表記, 期待する品詞, lex_row への追加指定, 仮名形)
    CASES = [
        # 組込側は「助数詞」をリストの完全一致で見ており、「助数詞可能」を取りこぼしていた
        ("咫", "助数詞", dict(p2="普通名詞", p3="助数詞可能"), "アタ"),
        # 具体的な品詞（助数詞・サ変・形状詞）はアルファベット判定より優先される
        ("atm", "助数詞", dict(p2="普通名詞", p3="助数詞可能"), "アトム"),
        ("ACCESS", "名詞サ変", dict(p2="普通名詞", p3="サ変可能"), "アクセス"),
        ("Academic", "名詞形動", dict(p1="形状詞", p2="一般"), "アカデミック"),
        # 具体的な情報が無い英字は従来どおりアルファベット
        ("IT", "アルファベット", {}, "アイティー"),
        ("星", "名詞", {}, "ホシ"),
    ]

    def _classify(self, config_path):
        rows = [lex_row(s, kana=k, **kw) for s, _, kw, k in self.CASES]
        with tempfile.TemporaryDirectory() as d:
            return {r[1]: r[2] for r in run_convert(rows, d, config_path)}

    def test_expected_pos(self):
        got = self._classify(CONFIG_PATH)
        for surface, expected, _kw, _kana in self.CASES:
            with self.subTest(surface=surface):
                self.assertEqual(got.get(surface), expected)

    def test_both_paths_agree(self):
        self.assertEqual(self._classify(CONFIG_PATH), self._classify(None))


class MatchConditionOperatorTest(unittest.TestCase):
    """JSONルールの演算子。_contains は「すべて含む」、_endswith は「いずれかで終わる」。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        with redirect_stdout(io.StringIO()):
            self.conv = convert_unidic.UnidicConverter(self._tmp.name, None)

    def tearDown(self):
        self._tmp.cleanup()

    def _match(self, match, **data):
        u = {"surface": "", "p1": "*", "p2": "*", "p3": "*", "p4": "*",
             "cType": "*", "cForm": "*"}
        u.update(data)
        return self.conv._match_condition(match, u)

    def test_endswith_is_not_contains(self):
        """surface_contains では「ずるける」まで拾ってしまう。"""
        self.assertTrue(self._match({"surface_endswith": "ずる"}, surface="論ずる"))
        self.assertFalse(self._match({"surface_endswith": "ずる"}, surface="ずるける"))
        self.assertTrue(self._match({"surface_contains": "ずる"}, surface="ずるける"))

    def test_endswith_list_is_any_of(self):
        m = {"surface_endswith": ["ずる", "ズル"]}
        self.assertTrue(self._match(m, surface="論ずる"))
        self.assertTrue(self._match(m, surface="アンズル"))
        self.assertFalse(self._match(m, surface="論じる"))

    def test_contains_list_is_all_of(self):
        m = {"cType_contains": ["五段", "カ行"]}
        self.assertTrue(self._match(m, cType="五段-カ行"))
        self.assertFalse(self._match(m, cType="五段-ガ行"))

    def test_equality_list_is_any_of(self):
        m = {"p4": ["姓", "名"]}
        self.assertTrue(self._match(m, p4="姓"))
        self.assertFalse(self._match(m, p4="地名"))

    def test_missing_key_defaults_to_asterisk(self):
        self.assertTrue(self._match({"cForm": "*"}))


if __name__ == "__main__":
    unittest.main()
