#!/usr/bin/env python3
"""辞書の各エントリを Mozc が「元から出せるか」を全件走査する（Windows専用）。

出力は「Mozc が既に出せるエントリ」の一覧で、`merge_unidics.py --exclude-list`
に渡すと重複登録を落とした差分辞書が作れる。

> [!WARNING]
> 走査中はユーザー辞書を空へ差し替えます。この間 IME からユーザー辞書は
> 引けません。26万件では1時間ほどかかります。
> 異常終了した場合は user_dictionary.db.abbackup から手動で戻してください。

結果は逐次書き出すので、中断しても --resume で続きから再開できます。

使い方:
    python eval/scan_system_coverage.py DICT.tsv -o eval/system_covered.tsv
    python eval/scan_system_coverage.py DICT.tsv -o eval/system_covered.tsv --resume
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mozc_ipc  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_entries(paths):
    rows = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            for line in f:
                c = line.rstrip("\n").rstrip("\r").split("\t")
                if len(c) >= 3:
                    rows.append((c[0], c[1], c[2]))
    return rows


def load_done(path):
    """既に判定済みの (reading, surface) を読み戻す。"""
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            if len(c) >= 2:
                done.add((c[0], c[1]))
    return done


def scan(client, entries, out_path, progress_path, topk, flush_every):
    covered = 0
    started = time.time()
    with open(out_path, "a", encoding="utf-8", newline="") as out, \
         open(progress_path, "a", encoding="utf-8", newline="") as prog:
        for n, (reading, surface, pos) in enumerate(entries, 1):
            try:
                _top, cands = client.convert(reading, limit=topk)
            except mozc_ipc.MozcError as e:
                print(f"  変換に失敗（スキップ）: {reading} ({e})", flush=True)
                continue
            prog.write(f"{reading}\t{surface}\n")
            if surface in cands:
                out.write(f"{reading}\t{surface}\t{pos}\n")
                covered += 1
            if n % flush_every == 0:
                out.flush()
                prog.flush()
                rate = n / (time.time() - started)
                remain = (len(entries) - n) / rate if rate else 0
                print(f"  {n:,}/{len(entries):,}  既存 {covered:,} "
                      f"({covered / n * 100:.1f}%)  "
                      f"{rate:.0f} 件/秒  残り {remain / 60:.0f} 分", flush=True)
    return covered


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dictionaries", nargs="+")
    ap.add_argument("-o", "--output", required=True,
                    help="Mozc が既に出せるエントリの書き出し先")
    ap.add_argument("-k", "--topk", type=int, default=10)
    ap.add_argument("--resume", action="store_true",
                    help="前回の続きから再開する")
    ap.add_argument("--flush-every", type=int, default=2000)
    ap.add_argument("--reload-wait", type=float, default=3.0)
    args = ap.parse_args(argv)

    progress_path = args.output + ".progress"
    entries = load_entries(args.dictionaries)

    if args.resume:
        done = load_done(progress_path)
        entries = [e for e in entries if (e[0], e[1]) not in done]
        print(f"再開: 判定済み {len(done):,} 件をスキップ")
    else:
        for p in (args.output, progress_path):
            if os.path.exists(p):
                os.remove(p)

    client = mozc_ipc.MozcClient()
    db = mozc_ipc.user_dictionary_path()
    print(f"mozc_server {client.server_version()}")
    print(f"走査対象 {len(entries):,} 件（上位{args.topk}件で判定）")
    print("走査中はユーザー辞書を空へ差し替えます。終了時に必ず復元します。\n")

    started = time.time()
    with mozc_ipc.user_dictionary_disabled(client, db, wait=args.reload_wait):
        covered = scan(client, entries, args.output, progress_path,
                       args.topk, args.flush_every)
    print(f"\n辞書を復元しました（{os.path.getsize(db):,} bytes）")

    total = len(entries)
    print(f"走査 {total:,} 件 / 所要 {(time.time() - started) / 60:.1f} 分")
    if total:
        print(f"Mozc が既に出せる: {covered:,} 件 ({covered / total * 100:.1f}%)")
        print(f"差分として残る    : {total - covered:,} 件")
    print(f"\n出力: {args.output}")
    print("次のように使います:")
    print(f"  python converter_scripts/merge_unidics.py --exclude-list {args.output} ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
