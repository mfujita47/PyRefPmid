# PyRefPmid: Markdown PubMed Referencer

`PyRefPmid.py` は、Markdown ファイル内に記述された PubMed ID (PMID) を検出し、PubMed API を利用して論文情報を取得し、整形された参考文献リスト (References) を自動生成・追記する Python スクリプトです。

以前に QRef という Qt ベースのアプリがあって、これは PMID で論文情報を取得するのが簡単で大変重宝していました。しかし 2010 年くらいに更新停止してしまいました。

私の場合は PubMed インデックスされた論文しか引用しないため、本文中に引用された PMID から文献リストが作成できれば十分であります。そこで上記 QRef 機能をさらに簡略化する方向性で、この PyRefPmid.py を作成しました。

## 主な機能

*   **PMID 抽出**: Markdown ファイル内から指定されたパターン（デフォルト: `[pm 12345678]()` または `[pmid 12345678]()`、大文字小文字区別なし）で PMID を抽出します。括弧 `()` 内の記述は無視されます。
*   **論文情報取得**: PubMed API を利用して、著者、タイトル、雑誌、年、巻号、ページ、DOI などの詳細情報を取得します。
*   **引用置換**: 本文中の PMID 引用を、出現順に基づいた参照番号（デフォルト: `(1)`）に置換します。
*   **参考文献リスト生成**: 取得した情報に基づき、ファイルの末尾に `References` セクションを生成・更新します。
*   **フォーマットカスタマイズ**: 引用形式、参考文献リストの各項目の表示形式、表示する著者数などをコマンドライン引数でカスタマイズできます。
*   **ヘッダーレベル調整**: `References` セクションのヘッダーレベル (`#` の数) を、本文中の他の主要セクションに合わせて自動調整します。
*   **ファイル選択**: 入力ファイルを指定しない場合、ファイル選択ダイアログが表示されます。

## 必要なもの

*   Python 3.x
*   `requests` ライブラリ

`requests` ライブラリがインストールされていない場合は、以下のコマンドでインストールしてください。

```bash
pip install requests
```

## 使用方法

### 基本的な使い方

コマンドラインで以下のように実行します。

```bash
python PyRefPmid.py <入力Markdownファイル名> [オプション]
```

例えば、`mydocument.md` を処理し、結果を `mydocument_cited.md` に保存する場合:

```bash
python PyRefPmid.py mydocument.md
```

入力ファイルを指定せずに実行すると、ファイル選択ダイアログが開きます。

```bash
python PyRefPmid.py
```

### 原稿ファイル内での引用方法

Markdown 原稿ファイル内で PubMed の文献を引用するには、デフォルトでは以下のいずれかの形式を使用します（大文字・小文字は区別されません）。

```markdown
[pm ここにPMID]()
[pmid ここにPMID]()
```

括弧 `()` 内に何か記述があっても無視されます。

例えば、PMID が `12345678` の文献を引用する場合、以下のいずれの形式でも認識されます。

```markdown
この研究は重要です [pm 12345678]()。
これも同じです [PMID 12345678](link text)。
```

スクリプトを実行すると、これらの引用符は自動的に参照番号（例: `(1)`）に置換され、対応する文献情報がファイルの末尾にある `References` セクションに追加されます。

**注意:** 引用の形式は `--pmid-pattern` コマンドライン引数で変更可能です。変更した場合は、原稿ファイル内の記述もそのパターンに合わせてください。

### コマンドライン引数

以下の引数でスクリプトの動作をカスタマイズできます。

*   **`input_file`** (位置引数)
    *   **説明**: 処理対象の Markdown ファイルのパス。
    *   **必須/任意**: 任意。省略するとファイル選択ダイアログが表示されます。

*   **`-o OUTPUT_FILE`, `--output_file OUTPUT_FILE`**
    *   **説明**: 処理結果を出力するファイルパス。
    *   **デフォルト**: 指定しない場合、入力ファイル名に `_cited` が付加されます (例: `mydocument_cited.md`)。

*   **`--pmid-pattern PMID_PATTERN`**
    *   **説明**: Markdown 内で PMID を抽出するための正規表現パターン。PMID は `(\d+)` でキャプチャする必要があります。大文字小文字は区別されません。
    *   **デフォルト**: `r'\[pm(?:id)?\s+(\d+)\]\([^)]*\)'` (例: `[pm 123]()`, `[PMID 123](link)`)

*   **`--author-threshold AUTHOR_THRESHOLD`**
    *   **説明**: 参考文献リストに表示する著者名の最大数。`0` で全員表示。
    *   **デフォルト**: `0`

*   **`--citation-format CITATION_FORMAT`**
    *   **説明**: 本文中の引用を置換する際の形式。`{number}` で参照番号を挿入します。
    *   **デフォルト**: `'({number})'`

*   **`--ref-item-format REF_ITEM_FORMAT`**
    *   **説明**: 参考文献リストの各項目の表示形式テンプレート。
    *   **利用可能なプレースホルダー**: `{number}`, `{authors}`, `{title}`, `{journal}`, `{year}`, `{volume}`, `{issue}`, `{pages}`, `{doi}`, `{pmid}`
    *   **デフォルト**: `'{number}. {authors}. {title}. {journal} {year};{volume}:{pages}. doi: {doi}. PMID: {pmid}.'`

*   **`--api-delay API_DELAY`**
    *   **説明**: PubMed API へのリクエスト間の待機時間 (秒)。NCBI の利用規約を遵守するため。
    *   **デフォルト**: `0.4`

*   **`--api-base-url API_BASE_URL`**
    *   **説明**: PubMed API のベース URL。通常は変更不要です。
    *   **デフォルト**: `'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'`

### 使用例

著者数を3名に制限し、引用形式を `[番号]` に変更して実行する場合:

```bash
python PyRefPmid.py report.md --author-threshold 3 --citation-format "[{number}]"
```

## 注意点

*   PubMed API の利用には制限があります。`--api-delay` を適切に設定してください（デフォルト値は NCBI のガイドラインに基づいています）。
*   存在しない PMID や取得に失敗した PMID については、参考文献リストにエラーメッセージが表示されます。
