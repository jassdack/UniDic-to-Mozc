import os
import sys
import itertools

from typing import Dict, Set, Tuple, List, Any

def merge_unidics(cwj_path, csj_path, output_path):
    # key: (reading, surface, pos) -> value: {sources, cost}
    # 型ヒントを明示して静的解析を助ける
    dictionary: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    def process_file(path, source_tag):
        if not os.path.exists(path):
            print(f"Warning: {path} not found.")
            return
        
        print(f"Processing: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = line.split('\t')
                if len(parts) < 4: continue
                
                reading, surface, pos, comment = parts[0], parts[1], parts[2], parts[3]
                
                cost_val = 99999
                if len(parts) >= 5:
                    try:
                        cost_val = int(parts[4])
                    except ValueError:
                        pass
                
                key = (reading, surface, pos)
                
                if key not in dictionary:
                    dictionary[key] = {"sources": {source_tag}, "cost": cost_val}
                else:
                    # すでに同じ(読み, 表記, 品詞)が見つかった場合の処理
                    current_entry = dictionary[key]
                    
                    # 万が一 current_entry が辞書でない場合、再初期化してスキップを防ぐ
                    if not isinstance(current_entry, dict):
                        dictionary[key] = {"sources": {source_tag}, "cost": cost_val}
                        continue

                    # sources がセットであることを保証する
                    if "sources" not in current_entry or not isinstance(current_entry["sources"], set):
                        current_entry["sources"] = {source_tag}
                    else:
                        current_entry["sources"].add(source_tag)
                    
                    # コストの更新（より小さい値を優先）
                    if cost_val < current_entry.get("cost", 99999):
                        current_entry["cost"] = cost_val

    process_file(cwj_path, "cwj")
    process_file(csj_path, "csj")

    print(f"Merging and splitting. Max 100,000 entries per file.")
    
    LIMIT = 100000
    written = 0
    file_count = 1
    
    # 出力ファイル名のベースを作成 (例: mozc_unidic_merged.tsv -> mozc_unidic_merged_1.tsv)
    base_name, ext = os.path.splitext(output_path)
    
    # 読み（五十音順）を第一キーとし、同音の中で単語生起コストが小さい（頻出）順、次に表記順にソート。
    sorted_keys: List[Tuple[str, str, str]] = sorted(
        dictionary.keys(), 
        key=lambda k: (k[0], dictionary[k].get("cost", 99999), k[1])
    )
    total_entries = len(sorted_keys)
    
    for i in range(0, total_entries, LIMIT):
        current_output_path = f"{base_name}_{file_count}{ext}"
        # インデックスを明示的に計算してスライスの型エラーを回避
        end_idx = i + LIMIT
        # itertools.islice を使用して、型チェッカーのスライス解釈エラーを回避しつつ安全にチャンクを取得
        chunk = list(itertools.islice(sorted_keys, i, end_idx))
        
        with open(current_output_path, 'w', encoding='utf-8') as f_out:
            for key in chunk:
                reading, surface, pos = key
                f_out.write(f"{reading}\t{surface}\t{pos}\t\n")
                written += 1
        
        print(f"  - Saved {len(chunk)} entries to: {current_output_path}")
        file_count += 1

    print(f"Done. Integrated entries: {written} (Total {file_count-1} files)")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python merge_unidics.py <cwj_tsv_path> <csj_tsv_path> <output_merged_tsv_path>")
        print("Example: python merge_unidics.py ./output_tsvs/mozc_cwj.tsv ./output_tsvs/mozc_csj.tsv output/mozc_unidic_merged.tsv")
    else:
        cwj = sys.argv[1]
        csj = sys.argv[2]
        out = sys.argv[3]
        merge_unidics(cwj, csj, out)
