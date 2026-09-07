# eval — 辞書品質の測定

## 何を測るか

`measure_injection.py` は、生成した辞書が**利用者が実際に打つ読みに対して何を注入するか**を測ります。

各テスト読みについて、辞書の寄与を4分類します。

| 分類 | 意味 |
|:--|:--|
| 純益 | 期待表記だけを追加した（競合を増やさない） |
| 混在 | 期待表記を追加したが、同時に N-1 件の競合も足した |
| 純ノイズ | 期待表記を含まず、競合だけを足した |
| 無関与 | 何も追加していない（＝辞書に無い） |

## 測っていないこと

Mozc の**最終的な候補順位**は測っていません。それはシステム辞書と Mozc の
コストモデルが決めるため、本スクリプト単体から変換精度は断定できません。
「純ノイズ」は「誤変換を起こした」ではなく「求められない候補だけを増やした」の意味です。

実変換精度の測定には `mozc_server` への IPC 接続が別途必要です（未実装）。

## 使い方

```bash
# 現状の配布辞書
python eval/measure_injection.py path/to/mozc_unidic_merged_?.tsv

# 品詞を除外した場合との比較
python eval/measure_injection.py path/to/mozc_unidic_merged_?.tsv --exclude-pos 人名
```

## テストセット

`testset_words.tsv` は `読み / 期待表記 / カテゴリ` の3列。124件。
カテゴリは `common` `homophone` `verb` `tech` `spoken` `academic` `place` `person`。

**このテストセットは手で書かれたものであり、構成が結果を左右します。**
`common` と `homophone` に厚みを置き、辞書が勝つべき層（`place` `person`
`academic`）も意図的に含めています。追加・修正して再測定してください。
