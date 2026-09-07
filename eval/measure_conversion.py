#!/usr/bin/env python3
"""ユーザー辞書の有無で実際の変換精度がどう変わるかを測る（Windows専用）。

measure_injection.py が「辞書が何を注入するか」を測るのに対し、こちらは
**稼働中の mozc_server に実際に変換させて**第1候補を比べる。

手順:
    1. 現在の user_dictionary.db のまま全件変換（辞書あり）
    2. 辞書を空へ差し替えて RELOAD、全件変換（辞書なし）
    3. 辞書を復元
辞書は必ず復元される。中断された場合は .abbackup が残る。

対象は **Mozc にインポート済みの任意のユーザー辞書**です。本プロジェクトの辞書に
限りません。テストセットも自前のものを渡せます。

前提:
    - mozc_server が起動していること
    - python eval/fetch_mozc_protos.py を実行済みであること
    - 計測対象の辞書が Mozc にインポート済みであること

使い方:
    python eval/measure_conversion.py                       # 語単位
    python eval/measure_conversion.py --testset eval/testset_sentences.tsv
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mozc_ipc  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TESTSET = os.path.join(HERE, "testset_words.tsv")

IMPROVED, REGRESSED, UNCHANGED_OK, UNCHANGED_NG = "改善", "悪化", "両方正解", "両方不正解"


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


def run_pass(client, cases, topn, label):
    results = {}
    for n, (reading, expected, _cat) in enumerate(cases, 1):
        top, cands = client.convert(reading, limit=topn)
        results[reading] = (top, cands)
        if n % 25 == 0:
            print(f"  {label}: {n}/{len(cases)}", flush=True)
    return results


def classify(with_ok, without_ok):
    if with_ok and not without_ok:
        return IMPROVED
    if without_ok and not with_ok:
        return REGRESSED
    return UNCHANGED_OK if with_ok else UNCHANGED_NG


def report(cases, with_d, without_d, topn):
    rows = []
    for reading, expected, cat in cases:
        w_top, w_c = with_d[reading]
        o_top, o_c = without_d[reading]
        rows.append({
            "reading": reading, "expected": expected, "category": cat,
            "with_top": w_top, "without_top": o_top,
            "with_top1": w_top == expected, "without_top1": o_top == expected,
            "with_topn": expected in w_c, "without_topn": expected in o_c,
            "verdict": classify(w_top == expected, o_top == expected),
        })

    n = len(rows)
    w1 = sum(r["with_top1"] for r in rows)
    o1 = sum(r["without_top1"] for r in rows)
    wn = sum(r["with_topn"] for r in rows)
    on = sum(r["without_topn"] for r in rows)

    print(f"\n{'=' * 68}")
    print(f" 変換精度 A/B（テスト {n} 件）")
    print(f"{'=' * 68}")
    print(f"\n{'指標':<22}{'辞書なし':>10}{'辞書あり':>10}{'差':>9}")
    print(f"{'第1候補一致':<20}{o1:>10}{w1:>10}{w1 - o1:>+9}")
    print(f"{'':<20}{o1 / n * 100:>9.1f}%{w1 / n * 100:>9.1f}%")
    print(f"{f'上位{topn}件に含む':<20}{on:>10}{wn:>10}{wn - on:>+9}")
    print(f"{'':<20}{on / n * 100:>9.1f}%{wn / n * 100:>9.1f}%")

    verdicts = Counter(r["verdict"] for r in rows)
    print(f"\n【第1候補の変化】")
    for v in (IMPROVED, REGRESSED, UNCHANGED_OK, UNCHANGED_NG):
        c = verdicts.get(v, 0)
        print(f"  {v:<10}{c:>5} 件 ({c / n * 100:5.1f}%)")

    print(f"\n【カテゴリ別 第1候補一致】")
    print(f"  {'カテゴリ':<12}{'件数':>5}{'なし':>7}{'あり':>7}{'差':>7}")
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    order = ["common", "homophone", "verb", "tech", "spoken",
             "academic", "place", "person"]
    for cat in sorted(by_cat, key=lambda c: order.index(c) if c in order else 99):
        rs = by_cat[cat]
        a = sum(x["with_top1"] for x in rs)
        b = sum(x["without_top1"] for x in rs)
        print(f"  {cat:<12}{len(rs):>5}{b:>7}{a:>7}{a - b:>+7}")

    for title, key in [("辞書によって正解した例", IMPROVED),
                       ("辞書によって不正解になった例", REGRESSED)]:
        picked = [r for r in rows if r["verdict"] == key]
        if picked:
            print(f"\n【{title}】{len(picked)} 件")
            for r in picked[:10]:
                print(f"  {r['reading']:<14} 期待={r['expected']:<8} "
                      f"なし={r['without_top']:<10} あり={r['with_top']}")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--testset", default=DEFAULT_TESTSET)
    ap.add_argument("--topn", type=int, default=10)
    ap.add_argument("--reload-wait", type=float, default=3.0)
    args = ap.parse_args(argv)

    cases = load_testset(args.testset)
    client = mozc_ipc.MozcClient()
    db = mozc_ipc.user_dictionary_path()
    print(f"mozc_server {client.server_version()}")
    print(f"user_dictionary.db {os.path.getsize(db):,} bytes")
    print(f"テスト {len(cases)} 件\n")

    print("[1/2] 辞書あり")
    with_d = run_pass(client, cases, args.topn, "あり")

    print("[2/2] 辞書なし（空辞書へ一時差替）")
    with mozc_ipc.user_dictionary_disabled(client, db, wait=args.reload_wait):
        without_d = run_pass(client, cases, args.topn, "なし")
    print(f"辞書を復元しました（{os.path.getsize(db):,} bytes）")

    report(cases, with_d, without_d, args.topn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
