import os
import sys
import argparse

# Mozc の 1 辞書あたりの上限は 1,000,000 語（kMaxEntrySize）。
# src/dictionary/user_dictionary_storage.cc:
#     constexpr size_t kMaxEntrySize = 1000000;
# インポート経路も同じ上限を使う（user_dictionary_importer.cc が IsDictionaryFull()
# 経由で entries_size() >= max_entry_size() を判定する）。
# Mozc 3.33.6089.100 に 267,413 語を1ファイルでインポートできることを実機で確認済み。
# したがって既定では分割せず、上限を超えたときだけ分割する。--limit で変更できる。
MOZC_MAX_ENTRY_SIZE = 1000000
LIMIT = MOZC_MAX_ENTRY_SIZE
DEFAULT_COST = 99999


def load_file(path, dictionary, accept=None, pos_seen=None, exclude_pairs=None):
    """中間TSVを読み込み、(reading, surface, pos) -> {cost, comment} に集約する。

    accept: 品詞を受け取り採否を返す述語。None なら全採用。
    pos_seen: 出現した品詞を記録する集合（フィルタ指定の綴り誤りを検出するため）。
    exclude_pairs: 除外する (読み, 表記) の集合。None なら除外しない。
    返り値は (採用行数, 品詞で落とした行数, 除外リストで落とした行数)。
    ファイルが無い場合は None。
    """
    if not os.path.exists(path):
        print(f"Warning: {path} not found.")
        return None

    print(f"Processing: {path}")
    loaded = skipped = excluded = 0
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
            if exclude_pairs is not None and (reading, surface) in exclude_pairs:
                excluded += 1
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
    return loaded, skipped, excluded


def load_exclude_list(path):
    """(読み, 表記) の除外リストを読む。3列目以降は無視する。

    eval/scan_system_coverage.py の出力をそのまま渡せる。
    """
    pairs = set()
    with open(path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            cols = line.rstrip('\n').rstrip('\r').split('\t')
            if len(cols) >= 2 and cols[0] and cols[1]:
                pairs.add((cols[0], cols[1]))
    return pairs


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
                  exclude_pos=(), only_pos=(), limit=None, exclude_pairs=None):
    # key: (reading, surface, pos) -> {"cost": int, "comment": str}
    dictionary = {}
    limit = LIMIT if limit is None else limit
    if limit < 1:
        raise ValueError("limit は 1 以上でなければなりません")
    if limit > MOZC_MAX_ENTRY_SIZE:
        print(f"Warning: limit {limit:,} が Mozc の上限 "
              f"{MOZC_MAX_ENTRY_SIZE:,} を超えています。インポートが失敗します。")
    accept = build_pos_filter(exclude_pos, only_pos)
    pos_seen = set()

    found_any = False
    total_skipped = total_excluded = 0
    for path in input_paths:
        result = load_file(path, dictionary, accept, pos_seen, exclude_pairs)
        if result is not None:
            found_any = True
            total_skipped += result[1]
            total_excluded += result[2]

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

    if total_excluded:
        print(f"Exclude list: dropped {total_excluded:,} entries.")

    print(f"Merging and splitting. Max {limit:,} entries per file.")

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
    for i in range(0, total_entries, limit):
        file_count += 1
        current_output_path = f"{base_name}_{file_count}{ext}"
        chunk = sorted_keys[i:i + limit]

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
    parser.add_argument("--exclude-list", default=None, metavar="FILE",
                        help="(読み, 表記) の除外リスト。Mozc が元から出せる語を"
                             "落として差分辞書を作るのに使う"
                             "（eval/scan_system_coverage.py の出力）")
    parser.add_argument("--limit", type=int, default=LIMIT, metavar="N",
                        help=f"1ファイルあたりの語数上限（既定 {LIMIT:,}）。"
                             f"Mozc の上限は {MOZC_MAX_ENTRY_SIZE:,} 語なので、"
                             f"分割せず1ファイルにまとめることもできる")
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
    exclude_pairs = None
    if args.exclude_list:
        if not os.path.exists(args.exclude_list):
            parser.error(f"除外リストが見つかりません: {args.exclude_list}")
        exclude_pairs = load_exclude_list(args.exclude_list)
        print(f"Exclude list: {len(exclude_pairs):,} pairs from {args.exclude_list}")

    return merge_unidics(inputs, output,
                         with_comment=not args.no_comment,
                         exclude_pos=_split_pos(args.exclude_pos),
                         only_pos=_split_pos(args.only_pos),
                         limit=args.limit,
                         exclude_pairs=exclude_pairs)


if __name__ == "__main__":
    sys.exit(main())
