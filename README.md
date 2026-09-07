# UniDic to Mozc Integration

**「法務・運用・品質」の課題を解決した、Mozc 拡張辞書システムとユーザー辞書**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![License: BSD-3](https://img.shields.io/badge/License-BSD--3-orange.svg)](UNIDIC_LICENSE.txt)
![Python: 3.x](https://img.shields.io/badge/Python-3.x-green.svg)
![Platform: Windows | macOS | Linux | ChromeOS](https://img.shields.io/badge/Platform-Win%20%7C%20Mac%20%7C%20Linux-lightgrey.svg)

---

## プロジェクト概要

本プロジェクト「UniDic to Mozc Integration」は、Mozc（Google 日本語入力）ユーザー辞書を最適化・統合するためのシステム、およびMozc用ユーザー辞書です。

国立国語研究所が編纂したコーパス「UniDic」の語彙（約102万語）を、Mozcの品詞体系へマッピングし、**約26.7万語の実用的な基本形**へと整理しています。

人名（約8.7万語）は既定の配布物に含みません。変換候補を大きく圧迫する一方、主要な姓は地名・固有名詞としても収録されているため、外しても語彙をほとんど失わないことを実測で確認しています（[測定結果](#辞書品質の測定)）。人名が必要な方は、別配布の人名辞書を追加インポートしてください。

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
5. 同様の手順で `_2.tsv`、`_3.tsv` を順番にインポートします（既定辞書は全3ファイル）。

#### 人名辞書（任意）

人名を多く入力する場合は、`mozc_unidic_names_*.zip` を同じ手順で**別の辞書として**追加インポートしてください。別辞書に分けておくと、変換候補が煩雑に感じたときに辞書ツールから一括で無効化できます。

> [!IMPORTANT]
> Mozcのユーザー辞書には「1ファイル最大10万語」の制限があるため、安全なサイズに自動分割されています。全語彙を取り込むために、分割されたすべてのファイルを必ずインポートしてください。

---

## 独自に辞書を生成したい方へ

自分好みにカスタマイズしたい方や、将来の新しいコーパスを適用させたい場合は、以下の手順で変換スクリプトを実行してください。

### 必要要件

- Python 3.x （※外部ライブラリへの依存は一切ありません。標準ライブラリのみで完結します。）
- [UniDic CWJ 最新版](https://clrd.ninjal.ac.jp/unidic/) / [UniDic CSJ 最新版](https://clrd.ninjal.ac.jp/unidic/) (lex.csv)
- Mozc または Google 日本語入力

#### 【動作確認済み環境】

以下の環境にて、正常に辞書生成・インポートできることを確認しています。

- **OS**: Windows 11 Pro
- **Python**: Python 3.13.5
- **IME**: Mozc 3.33.6089.100

### スクリプトの実行

```bash
# 1. 各辞典の抽出と最適化変換
#    -o で出力ファイル名を明示指定します（省略すると lex.csv の親ディレクトリ名から
#    導出されるため、両コーパスを同名ディレクトリに置いていると上書きされます）
python converter_scripts/convert_unidic.py "path/to/unidic-cwj/lex.csv" "./output_tsvs" -o mozc_cwj.tsv
python converter_scripts/convert_unidic.py "path/to/unidic-csj/lex.csv" "./output_tsvs" -o mozc_csj.tsv

# 2. 統合・重複排除と10万語分割出力
#    入力は3つ以上でも指定できます。最後の引数が出力先です（ディレクトリは自動作成）
#    --exclude-pos で品詞を落とせます（既定配布は人名を除外）
python converter_scripts/merge_unidics.py --exclude-pos 人名 \
  "./output_tsvs/mozc_cwj.tsv" "./output_tsvs/mozc_csj.tsv" "output/mozc_unidic_merged.tsv"
```

`convert_unidic.py` が出力する**中間TSVは5列**です（`読み / 表記 / 品詞 / コメント / 単語生起コスト`）。第5列のコストは `merge_unidics.py` が同音語の並べ替えに使い、最終出力では破棄します。したがって `merge_unidics.py` が出力する**最終TSVは4列**で、これが Mozc ユーザー辞書の仕様です。

`merge_unidics.py` の主なオプション:

| オプション | 効果 |
| :--- | :--- |
| `--exclude-pos POS[,POS...]` | 指定した品詞を出力から除外する（例: `--exclude-pos 人名`） |
| `--only-pos POS[,POS...]` | 指定した品詞のみを出力する（例: `--only-pos 人名`） |
| `--no-comment` | コメント列（`UniDic [語種] / 語彙素`）を空にする |

いずれも位置引数のどこに置いても動作します。指定した品詞が入力に1件も無い場合は警告が出るため、綴り誤りが黙って無視されることはありません。品詞名は [`config/mozc_pos_list.md`](config/mozc_pos_list.md) の見出しと一致させてください。

### リリース用辞書のビルド

[Releases](https://github.com/jassdack/UniDic-to-Mozc/releases) で配布している辞書は、以下の手順で生成しています。UniDic は **`_full` 版**（`lex.csv` を含むソース配布）が必要です。解析用軽量版には `lex.csv` が含まれません。

```bash
# UniDic CWJ / CSJ の _full 版から lex.csv を取り出す
unzip -j unidic-cwj-<version>_full.zip lex.csv -d unidic-cwj/
unzip -j unidic-csj-<version>_full.zip lex.csv -d unidic-csj/

# 変換
python converter_scripts/convert_unidic.py unidic-cwj/lex.csv ./tsv -o mozc_cwj.tsv
python converter_scripts/convert_unidic.py unidic-csj/lex.csv ./tsv -o mozc_csj.tsv

# 統合（既定辞書）。人名を除外し、サイズ優先でコメント列を空にする
python converter_scripts/merge_unidics.py --exclude-pos 人名 --no-comment \
  tsv/mozc_cwj.tsv tsv/mozc_csj.tsv merged/mozc_unidic_merged.tsv

# 人名辞書（任意配布）
python converter_scripts/merge_unidics.py --only-pos 人名 --no-comment \
  tsv/mozc_cwj.tsv tsv/mozc_csj.tsv names/mozc_unidic_names.tsv

# 配布用 zip
zip -9 mozc_unidic_merged_vX.Y.Z.zip merged/mozc_unidic_merged_?.tsv UNIDIC_LICENSE.txt
zip -9 mozc_unidic_names_vX.Y.Z.zip  names/mozc_unidic_names_?.tsv  UNIDIC_LICENSE.txt
```

> [!WARNING]
> 統合の入力には、必ず `convert_unidic.py` が出力した**5列の中間TSV**を使ってください。
> 配布済みの4列TSVを再度 `merge_unidics.py` に通すと、コスト列が失われて全て既定値になり、
> 同音語の並び順が壊れます。

### テストの実行

品詞マッピングと分割ロジックの回帰テストが付属しています（標準ライブラリのみ）。

```bash
python -m unittest discover -s tests
```

### 辞書品質の測定

生成した辞書が「利用者が実際に打つ読み」に対して何を注入するかを測る仕組みが [`eval/`](eval/) にあります（外部依存なし）。

```bash
python eval/measure_injection.py path/to/mozc_unidic_merged_?.tsv
python eval/measure_injection.py path/to/mozc_unidic_merged_?.tsv --exclude-pos 人名
```

124件のテスト読みに対する実測値（UniDic 202512 由来のデータ）:

| 指標 | 人名を含む場合 | **既定（人名なし）** |
| :--- | ---: | ---: |
| 語数 | 354,666 | **267,413** |
| 1読みあたり平均競合数 | 11.0 | **8.2** |
| 同音異義語カテゴリの競合数 | 31.1 | **24.9** |
| 注入1件あたりの有用率 | 8.5% | **11.4%** |
| 期待表記をカバーできた読み | 116 / 124 | **116 / 124** |
| 分割ファイル数 | 4 | **3** |

人名の除外によって**カバレッジは1件も落ちず**、競合だけが約25%減ります。測定の前提と限界は [`eval/README.md`](eval/README.md) を参照してください。

### 品詞判定の一致検証（リリース前に必須）

`convert_unidic.py` には品詞判定の経路が2つあり（JSON設定とその組込フォールバック）、片方だけを直すと静かに乖離します。`lex.csv` 全体で突き合わせるスクリプトを用意しています。

```bash
python eval/check_pos_agreement.py path/to/unidic-cwj/lex.csv path/to/unidic-csj/lex.csv
```

乖離が1件でもあれば終了コード 1 を返します。合成データのユニットテストでは実データの組み合わせを網羅できないため、**辞書を生成する前に必ず実行してください**。

> [!TIP]
> **品詞マッピングのカスタマイズ機能**
> `convert_unidic.py` は、内部的な判定ロジックとして `config/pos_mapping.json` をデフォルトで読み込みます。このJSONファイルを編集することで、Pythonコードを一切触ることなく品詞マッピングのルールを書き換えることが可能です。設定項目として利用可能な品詞の一覧は、👉 [**config/mozc_pos_list.md**](config/mozc_pos_list.md) をご参照ください。
> また、独自のJSONファイルを使用したい場合は、第3引数で直接指定できます：
> `python converter_scripts/convert_unidic.py "path/to/lex.csv" "./output" "custom_rules.json"`
>
> **ノイズ判定も設定で変えられます。**
>
> | キー | 既定 | 効果 |
> | :--- | :--- | :--- |
> | `noise_pos` | `["補助記号", "記号"]` | 品詞(p1)で落とす対象。`[]` にすると `(株)` `(社)` `α` `ε` などが拾える反面、`っ->ッ` のような語も入る（UniDic CWJ で計249語） |
> | `noise_goshu` | `[]` | 語種で落とす対象。`["記号"]` にすると `VR` `PK` 等の英字略語3,000語以上も失われるため既定は無効 |
>
> なお `句読点` と `顔文字` は、UniDic の該当エントリに読みが収録されていないため、`noise_pos` を空にしても出力されません。

---

## ライセンス (License)

本プロジェクトは、「変換スクリプト本体」と「生成される辞書データ」で適用されるライセンスが異なります。利用形態による権利と義務の**差異**に注意してください。

### 1. 変換ツール本体 (Source Code)

本リポジトリに含まれるPythonスクリプトは、**[MIT License](LICENSE)** の下で公開されています。ハッカビリティを最大化するため、コードの改変・再配布・商用利用は自由に行えますが、完全な無保証（AS IS）での提供となります。詳細はリポジトリ内の `LICENSE` ファイルをご参照ください。

### 2. 生成される辞書データ (Generated Dictionary Data)

本ツールによって変換・生成された辞書データ（TSVファイル）、および入力元となるコーパス「UniDic」のデータについては、国立国語研究所（NINJAL）が提示するトリプルライセンス（GPL v2.0 / LGPL v2.1 / 修正BSD）のうち、ユーザーの利便性を最大化するため **修正BSDライセンス（3条項BSDライセンス）** を選択して適用するものとします。

生成されたTSVデータを公開・再配布、または他のソフトウェアに組み込んで利用する場合は、必ず以下のファイルを確認し、著作権表示要件を満たしてください：
👉 [**UNIDIC_LICENSE.txt**](UNIDIC_LICENSE.txt)
