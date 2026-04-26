# 変更履歴

このプロジェクトの注目すべき変更はすべてこのファイルに記載されます。

形式は [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) に基づいており、
このプロジェクトは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に準拠しています。

## [3.1.0] - 2026-04-26

### 追加

- **NCBI Literature Citation API への移行**:
  - PubMed `esummary` から公式の `ctxp` エンドポイントへ変更。
  - 最初から完全な CSL-JSON を取得することで、従来のパースエラーを完全に解消。

## [3.0.0] - 2026-03-10

### 追加

- **CSL (Citation Style Language) システムへの移行**:
  - `citeproc-py` を導入し、世界中の学術雑誌規定（APA, IEEE, Nature, Frontiers 等）に準拠した引用・参考文献生成が可能に。
  - `--csl-style` オプションを追加。スタイル名（`apa` など）や `.csl` ファイルのパスを指定可能。
  - `--csl-locale` オプションを追加。

## [2.3.0] - 2026-03-10

### 追加

- **スマートイニシャル整形機能**:
  - `--author-name-format` において `{initials}` の直後に記号（ピリオドなど）がある場合、各イニシャル文字にその記号を適用するように改善。
  - 例: `--author-name-format "{last}, {initials}."` と指定した場合、著者名 "Fujita MT" が "Fujita, M.T." と出力される。

## [2.2.0] - 2026-02-03

### 追加

- **著者表示のカスタマイズ機能**:
  - `--author-display` オプションを追加。`--author-threshold` 超過時に実際に表示する著者数を個別に指定可能に。
  - 例: `--author-threshold 6 --author-display 3` で「6人以上の場合は最初の3人 + et al」という医学雑誌の投稿規定に対応。
  - 後方互換性を維持（`--author-display` 未指定時は従来どおり `threshold` と同数を表示）。

## [2.1.0] - 2026-02-03

### 変更

- **設定管理の一元化**:
  - `GlobalSettings` データクラスをデフォルト値の唯一の定義場所とし、`DEFAULT_SETTINGS` はそこから自動生成。
  - `parse_args` と `main` での冗長な `or DEFAULT_SETTINGS[...]` パターンを削除。

## [2.0.0] - 2026-02-03

### 追加

- **並列処理の実装**:
  - `concurrent.futures.ThreadPoolExecutor` による並列フェッチを実装。
  - APIキーの有無に応じたインテリジェントなレート制限（APIキーありで ~10req/s）。

## [1.3.0] - 2026-02-02

### 追加

- **スマートファイル選択**:
  - `_select_input_file()` を導入。単一 `.md` ファイルの自動検出、複数ファイルのメニュー選択、GUIフォールバックを実装。
- **著者名フォーマット機能**:
  - コマンドライン引数 `--author-name-format` を追加。`{last}, {initials}.` のような柔軟なフォーマット指定が可能に。
  - 内部的に `_parse_name` メソッドを追加し、PubMed の名前形式を姓とイニシャルに分解。
- **参考文献ロジックの刷新 (Clean Regeneration)**:
  - `_split_content` メソッドにより、既存の References セクションを完全に分離・削除してから再生成する方式に変更。
  - これにより自己参照やゴミデータの残留を防止。

### 変更

- **キャッシュ戦略の最適化**:
  - キャッシュファイルのデフォルト保存先を「入力ファイルと同じディレクトリ」に変更。
  - ファイル名を `入力ファイル名.json` (例: `paper.json`) に変更し、原稿ごとの管理を容易化。
- **コードベースの刷新**:
  - `logging` モジュールの削除（`print` による明確な CLI 出力へ移行）。
  - `tkinter` の遅延インポートによる起動高速化。
  - `GlobalSettings` データクラスへの設定集約と `frozen=True` 化。
  - クラス構造を `ReferenceBuilder` パターンに再編し、`PySlideSpeaker` との設計統一。
- **README の刷新**: 冗長な記述を削除し、引用形式の説明やコマンドラインオプションの一覧を詳細化。

## [1.1.0] - 2026-01-29

### 追加

- 設定を一元管理する `Config` クラスを追加。
- 論文データを構造化して扱うための `ArticleMetadata` データクラスを追加。
- ネットワーク通信の安定性を向上させるため、API リクエストにタイムアウト設定を追加。

### 変更

- `PyRefPmid.py` を単一ファイル内でモジュール化し、責任範囲（API通信、キャッシュ、解析、整形）ごとにクラスを分割：
  - `PubMedClient`
  - `CacheManager`
  - `CitationParser`
  - `ReferenceFormatter`
  - `PubMedProcessor`
- `PubMedProcessor` を `argparse` から疎結合にし、他のスクリプトからの再利用性を向上。
- 不要なインポートを削除し、コードベースを整理。
- `ask_for_file` ユーティリティ関数を `main` 関数の近くに移動し、構成を整理。

## [1.0.0] - 2025-05-22

### 追加

- PubMed API レスポンスのキャッシュメカニズムを追加。コマンドライン引数 (`--cache-file`, `--no-cache`) で設定可能。
- キャッシュファイルのパス指定とキャッシュ無効化のためのコマンドライン引数を追加。
- `LICENSE` ファイル (MIT ライセンス) を追加。
- プロジェクトの変更を追跡するための `CHANGELOG.md` ファイルを追加。
- コードの理解と保守性を向上させるため、`PubMedProcessor` クラス全体にわたって docstring と型ヒントを強化。
- `os.path` に代わり、すべてのパス操作に `pathlib` を使用。
- `black` を使用してコードフォーマットを適用。

### 変更

- 引用処理を最適化:
  - `extract_pmid_groups` が各 PMID グループのスパン情報を返すように変更。
  - `replace_citations` を更新し、このスパン情報を使用してテキスト内引用をより正確かつ効率的に置換するように変更。
- `PubMedProcessor.process_file` メソッドのシグネチャを更新し、`Path` オブジェクトを受け入れるように変更。
- デフォルトの参考文献アイテム形式 (`DEFAULT_REFERENCE_ITEM_FORMAT`) を更新し、クリック可能な PubMed リンクを含むように変更: `[{pubmed_id}](https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/)`。
- `README.md` を更新し、詳細な使用方法、キャッシュに関する情報、コマンドライン引数、ライセンス、および変更履歴へのリンクを追加。

### 修正

- 内部的にファイルパスに対して `Path` オブジェクトを一貫して使用するように修正。

## [0.1.0] - 2025-03-14

### 追加

- `PyRefPmid` の初期リリース。
- 正規表現を使用して Markdown ファイルから PMID を抽出する機能を追加。
- PubMed API (Entrez) から出版詳細 (タイトル、著者、ジャーナル、年、DOI) を取得する機能を追加。
- Markdown ファイルの末尾に取得した出版詳細をリストする「参考文献」セクションを生成する機能を追加。
- テキスト内引用 (例: `[PMID:123456, PMID:789012]`) を連番 (例: `[1, 2]`) に置き換える機能を追加。
- 入力ファイルと出力ファイルを指定するための基本的なコマンドラインインターフェースを追加。
- 入力ファイル内の既存のヘッダーに基づいて、「参考文献」セクションのヘッダーレベルを自動検出する機能を追加。
- コマンドラインで入力ファイルが提供されない場合に、GUI ファイルダイアログによる入力ファイル選択機能を追加。
