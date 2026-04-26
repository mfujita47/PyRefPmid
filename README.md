# 📚 PyRefPmid: Markdown PubMed Referencer (v3.1.1)

**PyRefPmid** は、Markdown 原稿内の PubMed ID (PMID) を自動検出し、PubMed API から書誌情報を取得して参考文献リスト (References) を自動生成する Python スクリプトです。**NCBI Literature Citation API** を採用し、高速で正確な引用生成が可能です。

## ✨ 主な機能

- 📡 **公式 Citation API 対応**: PubMed 公式の Literature Citation API を利用してデータを取得。
- 🎨 **CSL スタイルサポート**: `citeproc-py` を搭載。APA, IEEE, Vancouver, Nature など、数千種類以上の引用スタイルに対応。
- 🔄 **スマート・グルーピング**: 連続する PMID タグ（スペースや改行を挟む場合を含む）を自動的に検出し、`[1-3]` や `(Smith, 2023; Jones, 2024)` のように最適にグループ化。
- 📋 **既存構成の維持**: 文書内に既に `References` などの見出しがある場合、その章番号やレベル（`## 8. References` など）を維持したまま内容を更新。
- ⚡ **究極のパフォーマンス**: 単一パス走査アルゴリズムとオンデマンド・データ処理により、大規模な文書でも瞬時に処理。
- 📂 **スマートファイル選択**: フォルダ内のファイルを自動検出。複数ある場合はメニュー選択や GUI ダイアログを利用可能。

## 📦 必要なもの

- Python 3.9+
- `requests`
- `citeproc-py`

## 🚀 導入方法 (Installation)

```bash
pip install requests citeproc-py
```

## 💻 使用方法

### 🏁 基本的な実行

```bash
python PyRefPmid.py [入力ファイル] [オプション]
```

- スタイルを Vancouver にする場合:
  ```bash
  python PyRefPmid.py draft.md --csl-style elsevier-vancouver
  ```
- スタイルを APA にする場合:
  ```bash
  python PyRefPmid.py draft.md --csl-style apa
  ```

### ✍️ 原稿内での記述方法

Markdown 内で PMID を記述します。

- **リンク形式**: `[pm 12345678]()`
- **タグ形式**: `[pmid 12345678]`

### ⚙️ コマンドラインオプション

#### 🛠️ 基本オプション

- **`input_file`**
  - 入力ファイル。省略時はカレントディレクトリを検索。
- **`--csl-style`**
  - 使用する CSL スタイル名（`apa`, `nature` 等）または `.csl` ファイルへのパス。
- **`-o`, `--output-file`**
  - 出力先。デフォルトは `[入力ファイル名]_cited.md`。

## 🧑‍💻 作者 (Author)

- **mfujita47 (Mitsugu Fujita)** - [https://github.com/mfujita47](https://github.com/mfujita47)

## 📄 ライセンス

[MIT License](LICENSE)
