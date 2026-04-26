# 📚 PyRefPmid: Markdown PubMed Referencer (v3.0.0)

**PyRefPmid** は、Markdown 原稿内の PubMed ID (PMID) を自動検出し、PubMed API から書誌情報を取得して参考文献リスト (References) を自動生成する Python スクリプトです。

v3.0.0 より **CSL (Citation Style Language)** を全面的にサポートしました。これにより、APA, IEEE, Nature, Frontiers など、世界中の学術雑誌の投稿規定に合わせた正確な引用・参考文献リストの生成が可能です。

## ✨ 主な機能

- 📂 **スマートファイル選択**: フォルダ内の Markdown ファイルを自動検出。複数ある場合はメニュー選択や GUI ダイアログも利用可能。
- 🔄 **PMID 抽出 & 引用置換**: `[pm 12345678]()` 形式を検出し、指定した引用スタイルに自動置換。
- 🎨 **CSL スタイルサポート**: `citeproc-py` を搭載。数千種類以上の引用スタイルを `--csl-style` 一つで切り替え。
- 📡 **書誌情報取得 & キャッシュ**: PubMed API から情報を取得し、ローカルキャッシュにより高速に動作。
- 📋 **参考文献リスト自動生成**: `References` セクションを規定のスタイルで生成。再実行時は常に最新の状態に更新。
- ⚡ **高速な並列処理**: 大量の文献も数秒でフェッチ可能。

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

- スタイルを APA にする場合:
  ```bash
  python PyRefPmid.py draft.md --csl-style apa
  ```
- スタイルを IEEE にする場合:
  ```bash
  python PyRefPmid.py draft.md --csl-style ieee
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
  - 使用する CSL スタイル名（`apa`, `ieee`, `nature` 等）または `.csl` ファイルへのパス。
  - **デフォルト**: `apa`
- **`--csl-locale`**
  - 言語・地域設定。
  - **デフォルト**: `en-US`
- **`-o`, `--output-file`**
  - 出力先。デフォルトは `[入力ファイル名]_cited.md`。

#### 🔧 高度な設定

- **`--api-key`**: PubMed API キー。指定すると制限が緩和されます。
- **`--references-header`**: 文献セクションの見出し（デフォルト: `References`）。
- **`--no-cache`**: キャッシュを使用せずに実行。

## 🧑‍💻 作者 (Author)

- **mfujita47 (Mitsugu Fujita)** - [https://github.com/mfujita47](https://github.com/mfujita47)

## 📄 ライセンス

[MIT License](LICENSE)
