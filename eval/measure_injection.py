#!/usr/bin/env python3
"""ユーザー辞書が変換候補に何を注入するかを測定する（標準ライブラリのみ）。

測っているもの:
    テストセットの各「読み」に対して、この辞書が何件の候補を追加し、
    そのうち利用者が求める表記が含まれるか。

測っていないもの:
    Mozc の最終的な候補順位。それはシステム辞書と Mozc のコストモデルが
    決めるため、本スクリプトの結果から変換精度そのものは断定できない。
    ここで言う「純ノイズ」は「誤変換を引き起こした」ではなく
    「利用者が求めない候補だけを増やした」の意味である。

使い方:
    python eval/measure_injection.py DICT.tsv [DICT2.tsv ...]
    python eval/measure_injection.py --exclude-pos 人名,地名 DICT*.tsv
"""
import argparse
import os
import re
import sys
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_TESTSET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "testset_words.tsv")

# 純益 / 混在 / 純ノイズ / 無関与
GAIN, MIXED, NOISE, NEUTRAL = "純益", "混在", "純ノイズ", "無関与"


def natural_key(path):
    """merged_2.tsv が merged_10.tsv より先に来るよう数値順で並べる。"""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", os.path.basename(path))]


def load_dictionary(paths, exclude_pos=frozenset()):
    """読み -> [(表記, 品詞), ...] をファイル出現順（= コスト順ソート）で返す。"""
    index = defaultdict(list)
    total = kept = 0
    for path in sorted(paths, key=natural_key):
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                cols = line.rstrip("\n").rstrip("\r").split("\t")
                if len(cols) < 3:
                    continue
                reading, surface, pos = cols[0], cols[1], cols[2]
                total += 1
                if pos in exclude_pos:
                    continue
                index[reading].append((surface, pos))
                kept += 1
    return index, total, kept


def load_testset(path):
    cases = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                raise SystemExit(f"テストセットの列数が不正: {line!r}")
            cases.append(tuple(cols))
    return cases


def classify(injected, expected):
    if not injected:
        return NEUTRAL
    surfaces = [s for s, _ in injected]
    if expected not in surfaces:
        return NOISE
    return GAIN if len(injected) == 1 else MIXED


def evaluate(index, cases):
    rows = []
    for reading, expected, category in cases:
        injected = index.get(reading, [])
        surfaces = [s for s, _ in injected]
        rank = surfaces.index(expected) + 1 if expected in surfaces else None
        rows.append({
            "reading": reading, "expected": expected, "category": category,
            "contention": len(injected), "rank": rank,
            "verdict": classify(injected, expected),
            "injected": injected,
        })
    return rows


def report(rows, label, total_lines, kept_lines):
    print(f"\n{'=' * 68}")
    print(f" {label}")
    print(f" 辞書エントリ: {kept_lines:,} / {total_lines:,}")
    print(f"{'=' * 68}")

    verdicts = Counter(r["verdict"] for r in rows)
    n = len(rows)
    print(f"\n【全体】 テスト {n} 件")
    for v in (GAIN, MIXED, NOISE, NEUTRAL):
        c = verdicts.get(v, 0)
        print(f"  {v:<6} {c:>4} 件 ({c / n * 100:5.1f}%)")

    contentions = [r["contention"] for r in rows]
    injected_total = sum(contentions)
    useful = sum(1 for r in rows if r["rank"] is not None)
    print(f"\n  注入候補の総数        : {injected_total:,}")
    print(f"  うち期待表記          : {useful}  "
          f"(注入1件あたりの有用率 {useful / injected_total * 100:.2f}%)"
          if injected_total else "  注入なし")
    print(f"  1読みあたり平均競合数  : {injected_total / n:.1f}")
    print(f"  最大競合数            : {max(contentions)} "
          f"({max(rows, key=lambda r: r['contention'])['reading']})")

    ranks = [r["rank"] for r in rows if r["rank"] is not None]
    if ranks:
        top1 = sum(1 for x in ranks if x == 1)
        print(f"  期待表記の平均順位     : {sum(ranks) / len(ranks):.1f} "
              f"(辞書内のコスト順ソート基準)")
        print(f"  うち辞書内で1位        : {top1}/{len(ranks)}")

    print(f"\n【カテゴリ別】")
    print(f"  {'カテゴリ':<10} {'件数':>4} {'純益':>5} {'混在':>5} "
          f"{'純ノイズ':>7} {'無関与':>6} {'平均競合':>8}")
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    order = ["common", "homophone", "verb", "tech", "spoken",
             "academic", "place", "person"]
    for cat in sorted(by_cat, key=lambda c: order.index(c) if c in order else 99):
        rs = by_cat[cat]
        vc = Counter(r["verdict"] for r in rs)
        avg = sum(r["contention"] for r in rs) / len(rs)
        print(f"  {cat:<10} {len(rs):>4} {vc.get(GAIN, 0):>5} {vc.get(MIXED, 0):>5} "
              f"{vc.get(NOISE, 0):>7} {vc.get(NEUTRAL, 0):>6} {avg:>8.1f}")
    return verdicts, injected_total, useful


def show_worst(rows, limit=8):
    print(f"\n【競合が多い読み 上位{limit}】")
    for r in sorted(rows, key=lambda r: -r["contention"])[:limit]:
        pos_mix = Counter(p for _, p in r["injected"]).most_common(3)
        mix = " ".join(f"{p}:{c}" for p, c in pos_mix)
        rank = f"{r['rank']}位" if r["rank"] else "不在"
        print(f"  {r['reading']:<8} 期待={r['expected']:<6} 競合={r['contention']:>4} "
              f"期待の位置={rank:<5} [{mix}]")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dictionaries", nargs="+", help="Mozc ユーザー辞書 TSV")
    ap.add_argument("--testset", default=DEFAULT_TESTSET)
    ap.add_argument("--exclude-pos", default="",
                    help="除外する品詞をカンマ区切りで（例: 人名,地名）")
    ap.add_argument("--label", default=None)
    ap.add_argument("--worst", type=int, default=8)
    args = ap.parse_args(argv)

    exclude = frozenset(p for p in args.exclude_pos.split(",") if p)
    index, total, kept = load_dictionary(args.dictionaries, exclude)
    cases = load_testset(args.testset)
    rows = evaluate(index, cases)

    label = args.label or ("全体" if not exclude else f"{'/'.join(sorted(exclude))} 除外")
    report(rows, label, total, kept)
    if args.worst:
        show_worst(rows, args.worst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
