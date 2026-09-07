#!/usr/bin/env python3
"""Mozc の protobuf 定義を取得して Python モジュールへコンパイルする。

生成物（`eval/_mozc_proto/`）はリポジトリに含めない。Mozc は BSD-3 であり
再配布には著作権表示が要るため、ソースは同梱せず取得スクリプトのみを置く。

必要なもの:
    pip install grpcio-tools

使い方:
    python eval/fetch_mozc_protos.py
"""
import os
import re
import sys
import urllib.request

# 再現性のためコミットを固定する。更新する場合はここだけ変える。
MOZC_SHA = "9fbd649bea4c5e99cd8ad5e487213b26a953a376"
BASE_URL = f"https://raw.githubusercontent.com/google/mozc/{MOZC_SHA}/src/"
ROOT_PROTO = "protocol/commands.proto"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "_mozc_proto")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def fetch(rel, seen):
    """rel と、その import を再帰的に取得する。"""
    if rel in seen:
        return
    seen.add(rel)
    dest = os.path.join(OUT_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(BASE_URL + rel, timeout=60) as r:
        text = r.read().decode("utf-8")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"  {rel} ({len(text):,} bytes)")
    for imp in re.findall(r'^import\s+"([^"]+)";', text, re.M):
        if not imp.startswith("google/protobuf/"):
            fetch(imp, seen)


def main():
    try:
        from grpc_tools import protoc
    except ImportError:
        print("grpcio-tools が必要です: pip install grpcio-tools")
        return 1

    print(f"google/mozc @ {MOZC_SHA[:12]} から取得:")
    seen = set()
    fetch(ROOT_PROTO, seen)

    protos = [os.path.join(OUT_DIR, p) for p in sorted(seen)]
    rc = protoc.main(["protoc", "-I" + OUT_DIR, "--python_out=" + OUT_DIR] + protos)
    if rc != 0:
        print(f"protoc が失敗しました (exit {rc})")
        return rc

    # 生成した *_pb2.py を import できるようにする
    init = os.path.join(OUT_DIR, "protocol", "__init__.py")
    if not os.path.exists(init):
        open(init, "w", encoding="utf-8").close()

    print(f"\n{len(seen)} ファイルを {OUT_DIR} へ生成しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
