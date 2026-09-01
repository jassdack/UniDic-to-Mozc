import os
import sys
import argparse

LIMIT = 100000        # Mozc ユーザー辞書の 1 ファイルあたり上限
DEFAULT_COST = 99999


def load_file(path, dictionary):
    """中間TSVを読み込み、(reading, surface, pos) -> {cost, comment} に集約する。
    返り値は読み込んだ行数。ファイルが無い場合は None。"""
    if not os.path.exists(path):
        print(f"Warning: {path} not found.")
        return None

    print(f"Processing: {path}")
    loaded = 0
    with open(path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if not line: continue
            parts = line.split('\t')
            if len(parts) < 4: continue

            reading, surface, pos, comment = parts[0], parts[1], parts[2], parts[3]

            cost = DEFAULT_COST
            if len(parts) >= 5:
                try:
                    cost = int(parts[4])
                except ValueError:
                    pass

            loaded += 1
            key = (reading, surface, pos)
            existing = dictionary.get(key)
            if existing is None:
                dictionary[key] = {"cost": cost, "comment": comment}
            elif cost < existing["cost"]:
                # より頻出（低コスト）な出典側の情報を採用する
                existing["cost"] = cost
                existing["comment"] = comment
    return loaded


def merge_unidics(input_paths, output_path, with_comment=True):
    # key: (reading, surface, pos) -> {"cost": int, "comment": str}
    dictionary = {}

    found_any = False
    for path in input_paths:
        if load_file(path, dictionary) is not None:
            found_any = True

    if not found_any:
        print("Error: none of the input files could be read.")
        return 1

    print(f"Merging and splitting. Max {LIMIT:,} entries per file.")

    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    base_name, ext = os.path.splitext(output_path)

    # 読み（五十音順）を第一キーとし、同音の中で単語生起コストが小さい（頻出）順、次に表記順にソート。
    sorted_keys = sorted(dictionary, key=lambda k: (k[0], dictionary[k]["cost"], k[1]))
    total_entries = len(sorted_keys)

    if total_entries == 0:
        print("Error: no entries to write (all inputs were empty or malformed).")
        return 1

    written = 0
    file_count = 0
    for i in range(0, total_entries, LIMIT):
        file_count += 1
        current_output_path = f"{base_name}_{file_count}{ext}"
        chunk = sorted_keys[i:i + LIMIT]

        with open(current_output_path, 'w', encoding='utf-8', newline='') as f_out:
            for key in chunk:
                reading, surface, pos = key
                comment = dictionary[key]["comment"] if with_comment else ""
                # Mozc ユーザー辞書は 読み/表記/品詞/コメント の4列。第5列(コスト)はここで破棄する。
                f_out.write(f"{reading}\t{surface}\t{pos}\t{comment}\n")
                written += 1

        print(f"  - Saved {len(chunk):,} entries to: {current_output_path}")

    print(f"Done. Integrated entries: {written:,} (Total {file_count} files)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="convert_unidic.py が生成した中間TSVを統合し、10万語ごとに分割出力します。")
    parser.add_argument("inputs", nargs="+", help="中間TSV（2つ以上指定可）")
    parser.add_argument("output", help="出力TSVのベースパス（_1.tsv, _2.tsv ... が付与されます）")
    parser.add_argument("--no-comment", action="store_true",
                        help="コメント列を空にする（ファイルサイズ優先）")
    args = parser.parse_args(argv)
    return merge_unidics(args.inputs, args.output, with_comment=not args.no_comment)


if __name__ == "__main__":
    sys.exit(main())
