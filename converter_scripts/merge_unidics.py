import os
import sys
import argparse

LIMIT = 100000        # Mozc ユーザー辞書の 1 ファイルあたり上限
DEFAULT_COST = 99999


def load_file(path, dictionary, accept=None, pos_seen=None):
    """中間TSVを読み込み、(reading, surface, pos) -> {cost, comment} に集約する。

    accept: 品詞を受け取り採否を返す述語。None なら全採用。
    pos_seen: 出現した品詞を記録する集合（フィルタ指定の綴り誤りを検出するため）。
    返り値は (採用行数, 品詞フィルタで落とした行数)。ファイルが無い場合は None。
    """
    if not os.path.exists(path):
        print(f"Warning: {path} not found.")
        return None

    print(f"Processing: {path}")
    loaded = skipped = 0
    with open(path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if not line: continue
            parts = line.split('\t')
            if len(parts) < 4: continue

            reading, surface, pos, comment = parts[0], parts[1], parts[2], parts[3]

            if pos_seen is not None:
                pos_seen.add(pos)
            if accept is not None and not accept(pos):
                skipped += 1
                continue

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
    return loaded, skipped


def build_pos_filter(exclude_pos=(), only_pos=()):
    """品詞の採否を決める述語を返す。両方空なら None（フィルタなし）。"""
    exclude, only = frozenset(exclude_pos), frozenset(only_pos)
    if exclude and only:
        raise ValueError("exclude_pos と only_pos は同時に指定できません")
    if only:
        return lambda pos: pos in only
    if exclude:
        return lambda pos: pos not in exclude
    return None


def merge_unidics(input_paths, output_path, with_comment=True,
                  exclude_pos=(), only_pos=()):
    # key: (reading, surface, pos) -> {"cost": int, "comment": str}
    dictionary = {}
    accept = build_pos_filter(exclude_pos, only_pos)
    pos_seen = set()

    found_any = False
    total_skipped = 0
    for path in input_paths:
        result = load_file(path, dictionary, accept, pos_seen)
        if result is not None:
            found_any = True
            total_skipped += result[1]

    if not found_any:
        print("Error: none of the input files could be read.")
        return 1

    # 綴り誤りで意図せず全件通過するのを防ぐ
    requested = frozenset(exclude_pos) | frozenset(only_pos)
    unknown = sorted(requested - pos_seen)
    if unknown:
        print(f"Warning: 入力に存在しない品詞が指定されました: {', '.join(unknown)}")

    if total_skipped:
        kind = "only-pos" if only_pos else "exclude-pos"
        print(f"POS filter ({kind}): dropped {total_skipped:,} entries.")

    print(f"Merging and splitting. Max {LIMIT:,} entries per file.")

    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    base_name, ext = os.path.splitext(output_path)

    # 読み（五十音順）を第一キーとし、同音の中で単語生起コストが小さい（頻出）順、次に表記順にソート。
    sorted_keys = sorted(dictionary, key=lambda k: (k[0], dictionary[k]["cost"], k[1]))
    total_entries = len(sorted_keys)

    if total_entries == 0:
        print("Error: no entries to write (all inputs were empty, malformed, "
              "or removed by the POS filter).")
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


def _split_pos(value):
    return [p.strip() for p in value.split(",") if p.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="convert_unidic.py が生成した中間TSVを統合し、10万語ごとに分割出力します。")
    parser.add_argument("--no-comment", action="store_true",
                        help="コメント列を空にする（ファイルサイズ優先）")
    pos_group = parser.add_mutually_exclusive_group()
    pos_group.add_argument("--exclude-pos", default="", metavar="POS[,POS...]",
                           help="指定した品詞を出力から除外する（例: --exclude-pos 人名）")
    pos_group.add_argument("--only-pos", default="", metavar="POS[,POS...]",
                           help="指定した品詞のみを出力する（例: --only-pos 人名）")
    parser.add_argument("paths", nargs="*", metavar="INPUT [INPUT ...] OUTPUT",
                        help="中間TSV（2つ以上指定可）と、最後に出力TSVのベースパス"
                             "（_1.tsv, _2.tsv ... が付与されます）")
    # 可変長の位置引数の途中にオプションを挟む（a.tsv --no-comment out.tsv）と
    # argparse は位置引数を2グループに割ってしまい、片方しか受け取れない。
    # parse_known_args で残りを回収し、オプションの位置に依存しないようにする。
    args, extra = parser.parse_known_args(argv)
    unknown_flags = [x for x in extra if x.startswith("-")]
    if unknown_flags:
        parser.error(f"unrecognized arguments: {' '.join(unknown_flags)}")
    paths = args.paths + extra
    if len(paths) < 2:
        parser.error("入力の中間TSVと出力パスを指定してください")
    *inputs, output = paths
    return merge_unidics(inputs, output,
                         with_comment=not args.no_comment,
                         exclude_pos=_split_pos(args.exclude_pos),
                         only_pos=_split_pos(args.only_pos))


if __name__ == "__main__":
    sys.exit(main())
