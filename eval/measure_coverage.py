#!/usr/bin/env python3
"""この辞書が Mozc に「本当に足している」語がどれだけあるかを測る（Windows専用）。

辞書の価値は、Mozc が元から出せる語を重複登録することではなく、
**出せない語を出せるようにすること**にある。そこで辞書からエントリを
無作為抽出し、辞書なしの Mozc が同じ変換を出せるかどうかを直接調べる。

分類:
    既存    辞書なしでも上位K件に出る（＝重複登録。競合を増やすだけ）
    追加    辞書ありでのみ上位K件に出る（＝本当の貢献）
    未達    辞書ありでも上位K件に出ない（＝登録しても届いていない）

対象は **任意の Mozc ユーザー辞書 TSV** です。本プロジェクトの辞書に限りません。
測定したい辞書を Mozc にインポートした状態で実行してください。

使い方:
    python eval/measure_coverage.py DICT.tsv -n 2000
"""
import argparse
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mozc_ipc  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EXISTING, ADDED, UNREACHED = "既存", "追加", "未達"


def load_entries(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            for line in f:
                c = line.rstrip("\n").rstrip("\r").split("\t")
                if len(c) >= 3:
                    rows.append((c[0], c[1], c[2]))
    return rows


def scan(client, sample, topk, label):
    hits = {}
    for n, (reading, surface, _pos) in enumerate(sample, 1):
        _top, cands = client.convert(reading, limit=topk)
        hits[(reading, surface)] = surface in cands
        if n % 250 == 0:
            print(f"  {label}: {n}/{len(sample)}", flush=True)
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dictionaries", nargs="+", help="Mozc ユーザー辞書 TSV")
    ap.add_argument("-n", "--sample", type=int, default=2000)
    ap.add_argument("-k", "--topk", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--reload-wait", type=float, default=3.0)
    args = ap.parse_args(argv)

    rows = load_entries(args.dictionaries)
    random.seed(args.seed)
    sample = random.sample(rows, min(args.sample, len(rows)))

    client = mozc_ipc.MozcClient()
    db = mozc_ipc.user_dictionary_path()
    print(f"mozc_server {client.server_version()}")
    print(f"辞書 {len(rows):,} 件から {len(sample):,} 件を抽出（上位{args.topk}件で判定）\n")

    print("[1/2] 辞書あり")
    with_d = scan(client, sample, args.topk, "あり")

    print("[2/2] 辞書なし（空辞書へ一時差替）")
    with mozc_ipc.user_dictionary_disabled(client, db, wait=args.reload_wait):
        without_d = scan(client, sample, args.topk, "なし")
    print(f"辞書を復元しました（{os.path.getsize(db):,} bytes）")

    verdicts, by_pos, examples = Counter(), defaultdict(Counter), defaultdict(list)
    for reading, surface, pos in sample:
        k = (reading, surface)
        if without_d[k]:
            v = EXISTING
        elif with_d[k]:
            v = ADDED
        else:
            v = UNREACHED
        verdicts[v] += 1
        by_pos[pos][v] += 1
        if len(examples[v]) < 8:
            examples[v].append(f"{reading}->{surface}")

    n = len(sample)
    print(f"\n{'=' * 62}")
    print(f" 辞書の実質的な貢献（{n:,} 件を抽出）")
    print(f"{'=' * 62}\n")
    for v in (EXISTING, ADDED, UNREACHED):
        c = verdicts.get(v, 0)
        print(f"  {v:<6}{c:>7,} 件 ({c / n * 100:5.1f}%)   例: "
              f"{' / '.join(examples[v][:3])}")

    added = verdicts.get(ADDED, 0)
    print(f"\n  全 {len(rows):,} 件へ外挿すると、実際に変換を増やしているのは")
    print(f"  およそ {int(len(rows) * added / n):,} 件（{added / n * 100:.1f}%）")

    print(f"\n【品詞別】")
    print(f"  {'品詞':<12}{'件数':>6}{'既存':>7}{'追加':>7}{'未達':>7}{'追加率':>8}")
    for pos, c in sorted(by_pos.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
        t = sum(c.values())
        print(f"  {pos:<12}{t:>6}{c.get(EXISTING,0):>7}{c.get(ADDED,0):>7}"
              f"{c.get(UNREACHED,0):>7}{c.get(ADDED,0)/t*100:>7.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
