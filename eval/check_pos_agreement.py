#!/usr/bin/env python3
"""JSON設定経路と組込ロジック経路が同じ品詞を返すことを実データで検証する。

convert_unidic.py には品詞判定の経路が2つある。

  - JSON経路 : config/pos_mapping.json のルールを上から評価する
  - 組込経路 : JSONが無い/マッチしない場合に使われる決定木

両者は同じ結論を出す設計だが、片方だけを直すと静かに乖離する。
tests/ の合成データでは実データの組み合わせを網羅できないため、
リリース前に本スクリプトで lex.csv 全体を突き合わせる。

使い方:
    python eval/check_pos_agreement.py path/to/lex.csv [path/to/another/lex.csv]

乖離が1件でもあれば終了コード 1 を返す。
"""
import argparse
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "converter_scripts"))
import convert_unidic as cu  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "pos_mapping.json")


def compare(lex_paths, config_path, out_dir):
    json_conv = cu.UnidicConverter(out_dir, config_path)
    builtin_conv = cu.UnidicConverter(out_dir, None)

    pairs, examples = Counter(), {}
    scanned = judged = 0

    for path in lex_paths:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                scanned += 1
                if len(row) < cu.MIN_COLUMNS:
                    continue
                if json_conv.is_noise(row):
                    continue
                surface = json_conv.fullwidth_to_halfwidth(row[cu.COL_SURFACE])
                if not surface:
                    continue
                judged += 1
                a = json_conv.map_pos_mozc(row, surface)
                b = builtin_conv.map_pos_mozc(row, surface)
                if a != b:
                    key = (a, b)
                    pairs[key] += 1
                    examples.setdefault(key, (surface, row[cu.COL_P1], row[cu.COL_P2],
                                              row[cu.COL_P3], row[cu.COL_CTYPE]))
    return scanned, judged, pairs, examples


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lex_csv", nargs="+", help="UniDic の lex.csv")
    ap.add_argument("--config", default=CONFIG_PATH)
    args = ap.parse_args(argv)

    for p in args.lex_csv:
        if not os.path.exists(p):
            print(f"入力が見つかりません: {p}")
            return 2

    tmp = os.path.join(PROJECT_ROOT, "_pos_agreement_tmp")
    scanned, judged, pairs, examples = compare(args.lex_csv, args.config, tmp)
    try:
        os.rmdir(tmp)
    except OSError:
        pass

    total = sum(pairs.values())
    print(f"走査 {scanned:,} 行 / 判定対象 {judged:,} 行")
    if not total:
        print("乖離なし: JSON経路と組込経路は全件で一致しました。")
        return 0

    print(f"乖離 {total:,} 行 ({total / judged * 100:.3f}%)\n")
    print(f"{'JSON':<12}{'組込':<14}{'件数':>8}  例")
    for (a, b), n in pairs.most_common():
        s, p1, p2, p3, ct = examples[(a, b)]
        print(f"{a:<12}{b:<14}{n:>8}  {s} (p1={p1},p2={p2},p3={p3},cType={ct})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
