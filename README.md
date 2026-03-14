# UniDic to Mozc Integration

**「法務・運用・品質」の課題を解決した、Mozc 拡張辞書システムとユーザー辞書**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![License: BSD-3](https://img.shields.io/badge/License-BSD--3-orange.svg)](UNIDIC_LICENSE.txt)
![Python: 3.x](https://img.shields.io/badge/Python-3.x-green.svg)
![Platform: Windows | macOS | Linux | ChromeOS](https://img.shields.io/badge/Platform-Win%20%7C%20Mac%20%7C%20Linux-lightgrey.svg)

---

## プロジェクト概要

本プロジェクト「UniDic to Mozc Integration」は、Mozc（Google 日本語入力）ユーザー辞書を最適化・統合するためのシステム、およびMozc用ユーザー辞書です。

国立国語研究所が編纂した最高峰のコーパス「UniDic」の語彙（約102万語）を、Mozcのアルゴリズムに最適化させ、**約35.4万語の実用的な基本形**へと昇華させています。

> [!NOTE]
> 本プロジェクトのより詳細な設計思想、既存IME環境との比較、および品詞マッピングの統計データなどの技術的な詳細は、👉 [**Project.md（プロジェクト詳細説明書）**](Project.md) をご参照ください。

---

## インストールと使い方（導入方法）

本プロジェクト最大の特徴は、**C++コンパイラやBazel等の複雑なビルドチェインを一切必要としない**点にあります。OSを問わず、GUIの「辞書ツール」から直接インポートできます。

### 辞書のインポート手順

1. [Releases](https://github.com/jassdack/UniDic-to-Mozc/releases) ページから、生成済みの `mozc_unidic_merged_*.zip` (またはtsv形式) をダウンロードして展開します。
2. Mozc または Google 日本語入力の「辞書ツール」を開きます。
3. 「管理」>「新規辞書にインポート」を選択します。
4. 解凍した `mozc_unidic_merged_1.tsv` を指定し、インポートを実行します。
5. 同様の手順で `_2.tsv` 〜 `_4.tsv` までを順番にインポートします。

> [!IMPORTANT]
> Mozcのユーザー辞書には「1ファイル最大10万語」の制限があるため、安全なサイズに自動分割されています。全語彙を取り込むために、分割されたすべてのファイルを必ずインポートしてください。

---

## 独自に辞書を生成したい方へ

自分好みにカスタマイズしたい方や、将来の新しいコーパスを適用させたい場合は、以下の手順で変換スクリプトを実行してください。

### 必要要件

- Python 3.x （※外部ライブラリへの依存は一切ありません。標準ライブラリのみで完結します。）
- [UniDic CWJ 最新版](https://clrd.ninjal.ac.jp/unidic/) / [UniDic CSJ 最新版](https://clrd.ninjal.ac.jp/unidic/) (lex.csv)
  ‐ Mozc

#### 【動作確認済み環境】

以下の環境にて、正常に辞書生成・インポートできることを確認しています。

- **OS**: Windows 11 Pro
- **Python**: Python 3.13.5
- **IME**: Mozc 3.33.6089.100

### スクリプトの実行

```bash
# 1. 各辞典の抽出と最適化変換
python converter_scripts/convert_unidic.py "path/to/cwj/lex.csv" "./output_tsvs"
python converter_scripts/convert_unidic.py "path/to/csj/lex.csv" "./output_tsvs"

# 2. 統合・重複排除と10万語分割出力
# ※ 出力された各TSVを指定して統合
python converter_scripts/merge_unidics.py "./output_tsvs/mozc_cwj.tsv" "./output_tsvs/mozc_csj.tsv" "output/mozc_unidic_merged.tsv"
```

> [!TIP]
> **品詞マッピングのカスタマイズ機能**
> `convert_unidic.py` は、内部的な判定ロジックとして `config/pos_mapping.json` をデフォルトで読み込みます。このJSONファイルを編集することで、Pythonコードを一切触ることなく品詞マッピングのルールを書き換えることが可能です。設定項目として利用可能な品詞の一覧は、👉 [**config/mozc_pos_list.md**](config/mozc_pos_list.md) をご参照ください。
> また、独自のJSONファイルを使用したい場合は、第3引数で直接指定できます：
> `python converter_scripts/convert_unidic.py "path/to/lex.csv" "./output" "custom_rules.json"`

---

## ライセンス (License)

本プロジェクトは、「変換スクリプト本体」と「生成される辞書データ」で適用されるライセンスが異なります。利用形態による権利と義務の**差異**に注意してください。

### 1. 変換ツール本体 (Source Code)

本リポジトリに含まれるPythonスクリプトは、**[MIT License](LICENSE)** の下で公開されています。ハッカビリティを最大化するため、コードの改変・再配布・商用利用は自由に行えますが、完全な無保証（AS IS）での提供となります。詳細はリポジトリ内の `LICENSE` ファイルをご参照ください。

### 2. 生成される辞書データ (Generated Dictionary Data)

本ツールによって変換・生成された辞書データ（TSVファイル）、および入力元となるコーパス「UniDic」のデータについては、国立国語研究所（NINJAL）が提示するトリプルライセンス（GPL v2.0 / LGPL v2.1 / 修正BSD）のうち、ユーザーの利便性を最大化するため **修正BSDライセンス（3条項BSDライセンス）** を選択して適用するものとします。

生成されたTSVデータを公開・再配布、または他のソフトウェアに組み込んで利用する場合は、必ず以下のファイルを確認し、著作権表示要件を満たしてください：
👉 [**UNIDIC_LICENSE.txt**](UNIDIC_LICENSE.txt)
