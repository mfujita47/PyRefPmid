# 📚 PyRefPmid: Markdown PubMed Referencer (v3.1.1)

**PyRefPmid** は、Markdown 原稿内の PubMed ID (PMID) を自動検出し、PubMed API から書誌情報を取得して、指定した雑誌の規定に合わせた引用記号と参考文献リストを自動生成する Python スクリプトです。

医学論文の執筆や、日々の文献レビューのメモ作成時に、手作業で文献情報を入力・フォーマットする煩わしい手間を省きます。**NCBI Literature Citation API** を採用しており、正確な書誌データを高速に取得できます。

---

## 💡 CSL（Citation Style Language）とは？

CSLは、論文の「本文中の引用記号（例: `[1]`, `(Smith, 2023)`）」や「末尾の参考文献リストの書式」を自動で整えるための**世界標準のスタイル定義ファイル**です。

本ツールは `citeproc-py` を搭載しており、Nature、APA、Vancouverスタイルなど、何千種類ものジャーナル規定に一瞬で切り替えることができます。

- **スタイルの探し方**: [Zotero Style Repository](https://www.zotero.org/styles) のような検索サイトで、投稿先のジャーナル名（例: `nature`, `plos-one`, `anticancer-research`）を検索すると、対応する CSL スタイル名がわかります。
- **手間いらずの自動ダウンロード**: 使用したいスタイル名（例: `--csl-style nature`）を指定するだけでOKです。手元に `.csl` ファイルが無い場合は、本ツールが公式リポジトリから自動的にダウンロードして適用します。

---

## ✨ 主な機能

- 📡 **公式 Citation API 対応**: PubMed 公式の Literature Citation API を利用して最新のデータを取得。
- 🔄 **スマート・グルーピング**: 本文中の連続する PMID タグ（スペースや改行を挟む場合を含む）を自動的に検出し、`[1-3]` や `(Smith, 2023; Jones, 2024)` のように規定に合わせて最適にグループ化。
- 📋 **既存構成の維持**: 文書内に既に `References` などの見出しがある場合、その章番号や見出しレベル（例: `## 8. References`）を維持したまま内容をシームレスに更新。
- ⚡ **究極のパフォーマンス**: 一度取得した文献情報はローカルにキャッシュされるため、大規模な文書や繰り返し実行する際にも瞬時に処理が完了します。
- 📂 **スマートファイル選択**: フォルダ内のファイルを自動検出。対象ファイルが複数ある場合は、ターミナル上のメニューや GUI ダイアログから簡単に選択可能。

---

## 📦 必要な環境

- Python 3.9 以上
- 外部ライブラリ: `requests`, `citeproc-py`

```bash
# ライブラリのインストール
pip install requests citeproc-py
```

---

## 💻 使い方と動作例

### 1. 原稿内での記述方法

Markdown 内の引用したい箇所に、PMIDを以下のいずれかの形式で記述します。

- **タグ形式**: `[pmid: 12345678]` または `[pmid 12345678]`
- **リンク形式**: `[pm 12345678]()` （エディタでの見栄えを整えたい場合）

#### 📝 実行前の Markdown (例)

```markdown
最新の腫瘍免疫の研究において、CAR-T細胞の疲弊に関するメカニズムが議論されている [pmid: 31234567]。
また、関連する複数の報告 [pmid: 29876543] [pmid: 30123456] によれば...

## References
```

### 2. スクリプトの実行

ターミナルを開き、対象のファイルとスタイルを指定して実行します。

```bash
# 基本的な実行 (デフォルトで Vancouver スタイルが適用されます)
python PyRefPmid.py draft.md

# ジャーナルの規定 (例: Anticancer Research) を指定して実行する場合
python PyRefPmid.py draft.md --csl-style anticancer-research

# スタイルを APA 形式にする場合
python PyRefPmid.py draft.md --csl-style apa
```

#### ✨ 実行後の Markdown (Vancouverスタイルの場合)

```markdown
最新の腫瘍免疫の研究において、CAR-T細胞の疲弊に関するメカニズムが議論されている [1]。
また、関連する複数の報告 [2,3] によれば...

## References

1. Smith J, et al. Mechanisms of CAR-T cell exhaustion in solid tumors. Nature. 2019;571(7766):123-128.
2. Doe A, et al. Early markers of T cell dysfunction. Cell. 2018;174(1):45-56.
3. Johnson B. Overcoming immune evasion in glioblastoma. Cancer Res. 2020;80(5):101-110.
```

---

## ⚙️ コマンドラインオプション

- **`input_file`**
  - 入力ファイル。省略した場合は、カレントディレクトリ内の Markdown ファイルを自動検索し、選択プロンプトを表示します。
- **`--csl-style`**
  - 使用する CSL スタイル名（`apa`, `nature` 等）またはローカルにある `.csl` ファイルへのパスを指定します。
- **`-o`, `--output-file`**
  - 出力先のファイル名。デフォルトでは元のファイルを上書きせず、`[元のファイル名]_cited.md` として新しいファイルを出力します。

---

## 🧑‍💻 作者 (Author)

- **mfujita47 (Mitsugu Fujita)** - [https://github.com/mfujita47](https://github.com/mfujita47)

## 📄 ライセンス

[MIT License](LICENSE)
