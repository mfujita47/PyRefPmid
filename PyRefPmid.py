# -*- coding: utf-8 -*-
import argparse
import json
import logging
import os
import re
import requests
import tempfile
import textwrap
import time
import tkinter as tk
from collections import OrderedDict
from pathlib import Path  # pathlib をインポート
from tkinter import filedialog

# ロギング設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# --- ファイル選択ダイアログ関数 ---
def ask_for_file(
    title="ファイルを選択してください",
    filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
):
    """ファイル選択ダイアログを表示してファイルパスを取得する"""
    root = tk.Tk()
    root.withdraw()
    filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
    root.destroy()
    if not filepath:
        logging.warning("ファイルが選択されませんでした。")
        return None
    return filepath


class PubMedProcessor:
    """Markdown ファイル内の PubMed 引用を処理し、References リストを生成・置換するクラス"""

    DEFAULT_PMID_REGEX_PATTERN = r"\[pm(?:id)?\s+(\d+)\]\([^)]*\)"
    DEFAULT_AUTHOR_THRESHOLD = 0
    DEFAULT_CITATION_FORMAT = "({number})"
    DEFAULT_REFERENCE_ITEM_FORMAT = "{number}. {authors}. {title} {journal} {year};{volume}:{pages}. doi: {doi}. [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)"
    DEFAULT_PUBMED_API_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    DEFAULT_API_REQUEST_DELAY = 0.4
    DEFAULT_CACHE_FILENAME = ".pubmed_cache.json" # Default cache filename

    def __init__(
        self,
        pmid_regex_pattern: str | None = None,
        author_threshold: int | None = None,
        citation_format: str | None = None,
        ref_item_format: str | None = None,
        api_base_url: str | None = None,
        api_delay: float | None = None,
        cache_file: str | Path | None = None, # Can be a full path or a directory
        use_cache: bool = True,
    ):
        """
        PubMedProcessor を初期化します。

        Args:
            pmid_regex_pattern (str | None, optional):
                PMID を抽出する正規表現パターン。
                PMID自体をキャプチャグループ `(\\d+)` で囲む必要があります。
                デフォルトは `DEFAULT_PMID_REGEX_PATTERN`。
            author_threshold (int | None, optional):
                References に表示する著者名の最大数。0 を指定すると全員表示します。
                デフォルトは `DEFAULT_AUTHOR_THRESHOLD`。
            citation_format (str | None, optional):
                本文中の引用形式。`{number}` で参照番号（例: "1-3,5"）を挿入します。
                デフォルトは `DEFAULT_CITATION_FORMAT`。
            ref_item_format (str | None, optional):
                References の各項目形式。以下のプレースホルダーを使用できます:
                {number}, {authors}, {title}, {journal}, {year},
                {volume}, {issue}, {pages}, {doi}, {pmid}
                デフォルトは `DEFAULT_REFERENCE_ITEM_FORMAT`。
            api_base_url (str | None, optional):
                PubMed API のベース URL。
                デフォルトは `DEFAULT_PUBMED_API_BASE_URL`。
            api_delay (float | None, optional):
                PubMed API へのリクエスト間隔 (秒)。
                デフォルトは `DEFAULT_API_REQUEST_DELAY`。
            cache_file (str | Path | None, optional):
                キャッシュファイルのパスまたはキャッシュファイルを保存するディレクトリ。
                None の場合、OS の一時フォルダに `DEFAULT_CACHE_FILENAME` が作成されます。
                ディレクトリが指定された場合、そのディレクトリ内に `DEFAULT_CACHE_FILENAME` が作成されます。
                ファイルパスが指定された場合、そのパスが直接使用されます。
            use_cache (bool, optional):
                キャッシュを使用するかどうか。デフォルトは True。
        """
        self.pmid_regex_pattern = pmid_regex_pattern or self.DEFAULT_PMID_REGEX_PATTERN
        self.author_threshold = (
            author_threshold
            if author_threshold is not None
            else self.DEFAULT_AUTHOR_THRESHOLD
        )
        self.citation_format = citation_format or self.DEFAULT_CITATION_FORMAT
        self.ref_item_format = ref_item_format or self.DEFAULT_REFERENCE_ITEM_FORMAT
        self.api_base_url = api_base_url or self.DEFAULT_PUBMED_API_BASE_URL
        self.api_delay = (
            api_delay if api_delay is not None else self.DEFAULT_API_REQUEST_DELAY
        )
        self.pubmed_details = {}
        self.not_found_pmids = []
        self.pmid_to_number_map = {}
        self.use_cache = use_cache

        if not self.use_cache:
            self.cache_file = None # キャッシュ無効時は None
            self.cache_data = {}
            logging.info("キャッシュは無効化されています。")
        else:
            if cache_file:
                potential_path = Path(cache_file)
                if potential_path.is_dir():
                    self.cache_file = potential_path / self.DEFAULT_CACHE_FILENAME
                else: # ファイルパスとして扱う (親ディレクトリが存在するかは後で確認)
                    self.cache_file = potential_path
            else:
                self.cache_file = Path(tempfile.gettempdir()) / self.DEFAULT_CACHE_FILENAME

            # キャッシュファイルの親ディレクトリが存在するか確認し、なければ作成
            if self.cache_file:
                parent_dir = self.cache_file.parent
                if not parent_dir.exists():
                    try:
                        parent_dir.mkdir(parents=True, exist_ok=True)
                        logging.info(f"キャッシュディレクトリを作成しました: {parent_dir}")
                    except Exception as e:
                        logging.error(f"キャッシュディレクトリの作成に失敗しました: {parent_dir} - {e}")
                        # ディレクトリ作成失敗時はキャッシュを無効にするか、エラーを投げるか検討
                        # ここでは一時的にデフォルトの場所にフォールバックする (あるいはキャッシュ無効化)
                        logging.warning(f"キャッシュディレクトリ作成失敗のため、一時フォルダにキャッシュファイルを作成します。")
                        self.cache_file = Path(tempfile.gettempdir()) / self.DEFAULT_CACHE_FILENAME

            self.cache_data = {}
            self._load_cache() # _load_cache は self.cache_file を使用
            if self.cache_file:
                 logging.info(f"キャッシュファイルパス: {self.cache_file.resolve()}")
            else: # use_cache が False の場合など
                 logging.info("キャッシュファイルパスは設定されていません（キャッシュ無効）。")

    def extract_pmid_groups(self, markdown_content: str) -> list[tuple[list[str], tuple[int, int]]]:
        """
        Markdown コンテンツから連続する PMID プレースホルダーをグループとして抽出し、
        各グループ内で PMID をソートする。
        また、全体の出現順に基づいた pmid_to_number_map も作成する。

        Args:
            markdown_content (str): 処理対象の Markdown 文字列。

        Returns:
            list[tuple[list[str], tuple[int, int]]]:
                各要素が (ソート済みPMIDリスト, (開始オフセット, 終了オフセット)) のタプルのリスト。
                PMID が見つからない場合は空のリストを返す。
        """
        pmid_groups_with_spans = []  # (sorted_pmid_list, (start_offset, end_offset)) を格納
        raw_pmids_in_order = (
            []
        )  # 本文中の出現順（グループ化前）のPMIDリスト（文献番号割り当て用）

        # 1. 全てのPMIDマッチとその位置を取得
        matches = list(
            re.finditer(self.pmid_regex_pattern, markdown_content, flags=re.IGNORECASE)
        )
        if not matches:
            logging.info("PMID 形式の引用が見つかりませんでした。")
            self.pmid_to_number_map = {}
            return []

        current_group_pmids = []
        current_group_start_offset = -1
        current_group_text_end = 0

        for i, match in enumerate(matches):
            pmid = match.group(1)
            match_start, match_end = match.span()

            if not current_group_pmids:  # 最初のPMIDまたは新しいグループの開始
                current_group_pmids.append(pmid)
                current_group_start_offset = match_start
                current_group_text_end = match_end
            else:
                # 前のマッチの終わりと今のマッチの始まりの間にあるテキストを取得
                inter_text = markdown_content[current_group_text_end:match_start]
                if not inter_text.strip():  # 空白文字のみなら同じグループ
                    current_group_pmids.append(pmid)
                    current_group_text_end = match_end
                else:  # 新しいグループ
                    # 前のグループを処理して追加
                    if current_group_pmids:
                        # グループ内でPMIDを数値としてソート
                        sorted_group = sorted(current_group_pmids, key=int)
                        pmid_groups_with_spans.append(
                            (sorted_group, (current_group_start_offset, current_group_text_end))
                        )
                        raw_pmids_in_order.extend(sorted_group)  # 文献番号割り当て用
                    # 新しいグループを開始
                    current_group_pmids = [pmid]
                    current_group_start_offset = match_start
                    current_group_text_end = match_end

        # 最後のグループを処理
        if current_group_pmids:
            sorted_group = sorted(current_group_pmids, key=int)
            pmid_groups_with_spans.append(
                (sorted_group, (current_group_start_offset, current_group_text_end))
            )
            raw_pmids_in_order.extend(sorted_group)

        # pmid_to_number_map の作成 (全体の出現順とグループ内ソートを考慮)
        unique_ordered_pmids_for_numbering = list(
            OrderedDict.fromkeys(raw_pmids_in_order)
        )
        self.pmid_to_number_map = {
            pmid: i + 1 for i, pmid in enumerate(unique_ordered_pmids_for_numbering)
        }

        logging.info(f"抽出・ソートされた PMID グループ (スパン情報付き): {pmid_groups_with_spans}")
        logging.info(
            f"PMID と番号のマッピング (文献リスト用): {self.pmid_to_number_map}"
        )

        return pmid_groups_with_spans

    def _load_cache(self) -> None:
        """キャッシュファイルからデータを読み込む"""
        if not self.use_cache or not self.cache_file: # self.cache_file が None の場合をチェック
            return

        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache_data = json.load(f)
                logging.info(f"キャッシュファイルを読み込みました: {self.cache_file.resolve()}")
            else:
                logging.info(f"キャッシュファイルが見つかりません ({self.cache_file.resolve()})。新規に作成されます。")
                self.cache_data = {}
        except json.JSONDecodeError:
            logging.warning(
                f"キャッシュファイル '{self.cache_file.resolve()}' の形式が不正です。キャッシュは無視されます。"
            )
            self.cache_data = {}
        except Exception as e:
            logging.error(f"キャッシュファイルの読み込み中にエラーが発生しました ({self.cache_file.resolve()}): {e}")
            self.cache_data = {}

    def _save_cache(self) -> None:
        """現在のキャッシュデータをファイルに保存する"""
        if not self.use_cache or not self.cache_file: # self.cache_file が None の場合をチェック
            return
        try:
            # 保存前に親ディレクトリの存在を再確認（動的に変更される可能性は低いが念のため）
            parent_dir = self.cache_file.parent
            if not parent_dir.exists():
                parent_dir.mkdir(parents=True, exist_ok=True)

            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache_data, f, ensure_ascii=False, indent=2)
            logging.info(f"キャッシュをファイルに保存しました: {self.cache_file.resolve()}")
        except Exception as e:
            logging.error(f"キャッシュファイルの保存中にエラーが発生しました ({self.cache_file.resolve()}): {e}")

    def _get_details_from_cache(self, pmids: list[str]) -> tuple[dict, list[str], list[str]]:
        """指定された PMID リストからキャッシュに存在する詳細を取得する

        Args:
            pmids (list[str]): 詳細を取得する PMID のリスト。

        Returns:
            tuple[dict, list[str], list[str]]:
                (キャッシュから取得した詳細の辞書, キャッシュになかったPMIDのリスト, キャッシュ内でエラーだったPMIDのリスト)
        """
        details_from_cache = {}
        pmids_not_in_cache = []
        not_found_in_cache = [] # キャッシュにはあったが、エラーエントリだったPMID

        if not self.use_cache or not self.cache_file: # キャッシュが無効またはファイルパスがない場合
            return {}, list(pmids), [] # 全てキャッシュになしとして返す

        for pmid in pmids:
            if pmid in self.cache_data:
                if "error" not in self.cache_data[pmid]:
                    logging.info(f"PMID {pmid} はキャッシュから取得しました。")
                    details_from_cache[pmid] = self.cache_data[pmid]
                else:
                    logging.info(f"PMID {pmid} はキャッシュにエラーとして記録されていました。APIで再試行します。")
                    pmids_not_in_cache.append(pmid) # APIで再取得を試みる
                    not_found_in_cache.append(pmid) # エラーだったことを記録
            else:
                pmids_not_in_cache.append(pmid)
        return details_from_cache, pmids_not_in_cache, not_found_in_cache

    def _fetch_details_from_api(self, pmids_to_fetch: list[str]) -> tuple[dict, list[str]]:
        """指定された PMID リストの詳細を PubMed API から取得する

        Args:
            pmids_to_fetch (list[str]): API で詳細を取得する PMID のリスト。

        Returns:
            tuple[dict, list[str]]: (APIから取得した詳細の辞書, APIで見つからなかったPMIDのリスト)
        """
        if not pmids_to_fetch:
            return {}, []
        logging.info(f"API で取得する PMID ({len(pmids_to_fetch)}件): {pmids_to_fetch}")
        pmid_string = ",".join(pmids_to_fetch)
        url = (
            f"{self.api_base_url}esummary.fcgi?db=pubmed&id={pmid_string}&retmode=json"
        )
        api_details = {}
        api_not_found = []
        logging.info(f"PubMed API にリクエスト中: {url}")
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            logging.info("PubMed API からレスポンスを受信")
            results = data.get("result")
            if not results or "uids" not in results:
                logging.warning("PubMed API から有効な結果が得られませんでした。")
                api_not_found.extend(pmids_to_fetch)
                for pmid in pmids_to_fetch:
                    api_details[pmid] = {"error": "Not found in API response"}
                return api_details, api_not_found
            returned_uids = results.get("uids", [])
            requested_pmids_set = set(pmids_to_fetch)
            returned_uids_set = set(returned_uids)
            missing_in_response = list(requested_pmids_set - returned_uids_set)
            if missing_in_response:
                logging.warning(
                    f"API レスポンスに以下の PMID が含まれていません: {missing_in_response}"
                )
                api_not_found.extend(missing_in_response)
                for missing_pmid in missing_in_response:
                    api_details[missing_pmid] = {"error": "Not found in API response"}
            for pmid in returned_uids:
                if pmid not in results:
                    logging.warning(
                        f"PMID {pmid} の詳細情報が results 内に見つかりません。"
                    )
                    if pmid not in api_not_found:
                        api_not_found.append(pmid)
                    api_details[pmid] = {"error": "Details not found in results dict"}
                    continue
                entry = results[pmid]
                if "error" in entry:
                    logging.warning(
                        f"PMID {pmid} の詳細取得で API エラー: {entry['error']}"
                    )
                    if pmid not in api_not_found:
                        api_not_found.append(pmid)
                    api_details[pmid] = entry
                    continue
                authors_list = entry.get("authors", [])
                author_names = [a.get("name", "N/A") for a in authors_list]
                if (
                    self.author_threshold > 0
                    and len(author_names) > self.author_threshold
                ):
                    authors = (
                        ", ".join(author_names[: self.author_threshold]) + ", et al"
                    )
                else:
                    authors = ", ".join(author_names)
                articleids = entry.get("articleids", [])
                doi = next(
                    (
                        aid.get("value", "")
                        for aid in articleids
                        if aid.get("idtype") == "doi"
                    ),
                    "",
                )
                if not doi and entry.get("elocationid", "").startswith("doi:"):
                    doi = entry.get("elocationid", "").replace("doi: ", "")
                api_details[pmid] = {
                    "authors": authors,
                    "year": entry.get("pubdate", "").split(" ")[0],
                    "title": entry.get("title", "N/A"),
                    "journal": entry.get("source", "N/A"),
                    "volume": entry.get("volume", ""),
                    "issue": entry.get("issue", ""),
                    "pages": entry.get("pages", ""),
                    "pmid": pmid,
                    "doi": doi,
                }
                time.sleep(self.api_delay)
        except requests.exceptions.RequestException as e:
            logging.error(f"PubMed API への接続に失敗しました - {e}")
            api_not_found.extend(pmids_to_fetch)
            for pmid in pmids_to_fetch:
                api_details[pmid] = {"error": f"API connection failed: {e}"}
        except Exception as e:
            logging.error(
                f"PubMed API データ処理中に予期せぬエラーが発生しました - {e}"
            )
            api_not_found.extend(pmids_to_fetch)
            for pmid in pmids_to_fetch:
                api_details[pmid] = {"error": f"Unexpected error during API fetch: {e}"}
        return api_details, list(set(api_not_found))

    def fetch_pubmed_details(self, pmids: list[str]) -> tuple[dict, list[str]]:
        """PubMed API またはキャッシュを使用して PMID リストに対応する論文詳細を取得する

        Args:
            pmids (list[str]): 詳細を取得する PMID のリスト。

        Returns:
            tuple[dict, list[str]]: (取得した論文詳細の辞書, 見つからなかったPMIDのリスト)
        """
        if not pmids:
            logging.warning("取得対象の PMID がありません。")
            return {}, []
        details_from_cache, pmids_to_fetch, not_found_in_cache = (
            self._get_details_from_cache(pmids)
        )
        api_details, api_not_found = self._fetch_details_from_api(pmids_to_fetch)
        final_details = {**details_from_cache, **api_details}
        final_not_found = list(set(not_found_in_cache + api_not_found))  # 重複除去
        if self.use_cache and api_details:
            for pmid, detail_data in api_details.items():
                self.cache_data[pmid] = detail_data
            self._save_cache()
        self.pubmed_details = final_details
        self.not_found_pmids = final_not_found
        valid_details_count = sum(1 for d in final_details.values() if "error" not in d)
        logging.info(
            f"取得またはキャッシュから読み込んだ有効な論文詳細数: {valid_details_count}"
        )
        if final_not_found:
            logging.warning(
                f"見つからなかった、または詳細取得に失敗した PMID ({len(final_not_found)}件): {final_not_found}"
            )
        return final_details, final_not_found

    def _format_reference_item(self, details: dict, number: int) -> str:
        """指定されたフォーマット文字列に従って References の項目を整形する

        Args:
            details (dict): 整形する論文詳細データ。
            number (int): 参照番号。

        Returns:
            str: 整形された参照項目の文字列。
        """
        try:
            return self.ref_item_format.format(
                number=number,
                authors=details.get("authors", "N/A"),
                year=details.get("year", "N/A"),
                title=details.get("title", "N/A"),
                journal=details.get("journal", "N/A"),
                volume=details.get("volume", ""),
                issue=details.get("issue", ""),
                pages=details.get("pages", ""),
                pmid=details.get("pmid", "N/A"),
                doi=details.get("doi", ""),
            ).strip()
        except KeyError as e:
            logging.error(
                f"参照項目のフォーマット中にエラーが発生しました。キー: {e}, フォーマット: {self.ref_item_format}, 詳細: {details}"
            )
            return f"{number}. [PMID {details.get('pmid', 'N/A')}] - フォーマットエラー"
        except Exception as e:
            logging.error(
                f"参照項目のフォーマット中に予期せぬエラーが発生しました: {e}"
            )
            return f"{number}. [PMID {details.get('pmid', 'N/A')}] - 不明なフォーマットエラー"

    def create_references_section(self, header: str) -> str:
        """References セクションの Markdown 文字列を生成する

        Args:
            header (str): References セクションのヘッダー文字列 (例: "## References")。

        Returns:
            str: 生成された References セクションの Markdown 文字列。
        """
        if not self.pubmed_details:
            logging.info(
                "論文詳細データがないため、References セクションは生成されません。"
            )
            return ""
        items = []
        for pmid, number in self.pmid_to_number_map.items():
            details = self.pubmed_details.get(pmid)
            if details and "error" not in details:
                item_str = self._format_reference_item(details, number)
                items.append(item_str)
            else:
                error_msg = (
                    details.get("error", "不明なエラー") if details else "取得失敗"
                )
                items.append(
                    f"{number}. [PMID {pmid}] - 論文情報の取得に失敗しました ({error_msg})。"
                )
        if not items:
            logging.info(
                "有効な参照項目がないため、References セクションは生成されません。"
            )
            return ""
        return f"\n\n{header}\n\n" + "\n".join(items)

    def detect_header_level(self, markdown_content: str) -> int:
        """本文中の Markdown コンテンツから主要セクションのヘッダーレベルを検出する

        Args:
            markdown_content (str): ヘッダーレベルを検出する Markdown 文字列。

        Returns:
            int: 検出されたヘッダーレベル。見つからない場合はデフォルトで 2 を返す。
        """
        matches = re.findall(
            r"^(#+)\s+(Introduction|Methods|Results|Discussion|Conclusion|Background|Case Report|Abstract|はじめに|方法|結果|考察|結論|背景|症例報告|要旨)",
            markdown_content,
            re.MULTILINE | re.IGNORECASE,
        )
        if matches:
            level = len(matches[0][0])
            logging.info(f"主要セクションのヘッダーレベル {level} を検出しました。")
            return level
        else:
            logging.warning(
                "主要セクションが見つかりませんでした。デフォルトのヘッダーレベル 2 を使用します。"
            )
            return 2

    def _format_citation_numbers(self, numbers: list[int]) -> str:
        """ソート済みの引用番号リストを整形する (例: "1,3-5")

        Args:
            numbers (list[int]): 整形する引用番号のリスト。

        Returns:
            str: 整形された引用番号の文字列。
        """
        if not numbers:
            return ""

        numbers = sorted(list(set(numbers)))  # 念のためソートと重複除去
        if not numbers:
            return ""

        ranges = []
        start_range = numbers[0]
        end_range = numbers[0]

        for i in range(1, len(numbers)):
            if numbers[i] == end_range + 1:
                end_range = numbers[i]
            else:
                if start_range == end_range:
                    ranges.append(str(start_range))
                elif end_range == start_range + 1:  # 2つ連続の場合はカンマ区切り
                    ranges.append(f"{start_range},{end_range}")
                else:  # 3つ以上連続の場合はハイフン
                    ranges.append(f"{start_range}-{end_range}")
                start_range = numbers[i]
                end_range = numbers[i]

        # 最後の範囲を追加
        if start_range == end_range:
            ranges.append(str(start_range))
        elif end_range == start_range + 1:
            ranges.append(f"{start_range},{end_range}")
        else:
            ranges.append(f"{start_range}-{end_range}")

        return ",".join(ranges)

    def _citation_replacer(self, match: re.Match) -> str:
        """re.sub のコールバック関数: マッチした PMID 参照を置換する (新しいロジックでは直接使われない可能性が高い)

        Args:
            match (re.Match): 正規表現のマッチオブジェクト。

        Returns:
            str: 置換後の文字列、またはエラー時は元のマッチ文字列。
        """
        # この関数は、replace_citations の新しい実装では直接使用されない。
        # グループ単位での置換が必要なため。
        # 互換性や部分的な使用のために残す場合は注意が必要。
        try:
            pmid = match.group(1)
            if (pmid in self.pmid_to_number_map):
                number = self.pmid_to_number_map[pmid]
                # citation_format は {number} を含む。
                # 単一PMIDの場合のフォーマット。
                return self.citation_format.format(number=number)
            else:
                logging.warning(
                    f"PMID {pmid} は番号マップに見つかりません。引用符は置換されません: {match.group(0)}"
                )
                return match.group(0)
        except IndexError:
            logging.error(
                f"PMID パターン '{self.pmid_regex_pattern}' が PMID をキャプチャしませんでした。マッチ: {match.group(0)}"
            )
            return match.group(0)
        except KeyError as e:
            logging.error(
                f"引用符のフォーマット中にエラーが発生しました。キー: {e}, フォーマット: {self.citation_format}"
            )
            return match.group(0)
        except Exception as e:
            logging.error(
                f"引用符の置換中に予期せぬエラーが発生しました ({match.group(0) if match else 'N/A'}): {e}"
            )
            return match.group(0) if match else ""

    def replace_citations(self, markdown_content: str, pmid_groups_with_spans: list[tuple[list[str], tuple[int, int]]]) -> str:
        """Markdown コンテンツ内の PMID 参照を指定された形式に置換する (グループ対応、スパン情報利用)

        Args:
            markdown_content (str): 処理対象の Markdown 文字列。
            pmid_groups_with_spans (list[tuple[list[str], tuple[int, int]]]):
                `extract_pmid_groups` から返される、PMIDグループとスパン情報のリスト。

        Returns:
            str: 引用が置換された Markdown 文字列。
        """
        if not pmid_groups_with_spans:
            logging.info("置換対象の PMID グループがありません。")
            return markdown_content

        new_content_parts = []
        last_processed_end = 0

        for group_pmids_sorted, (group_start_pos, group_end_pos) in pmid_groups_with_spans:
            # グループ内のPMIDに対応する引用番号を取得
            citation_numbers_for_group = []
            for pmid_in_group in group_pmids_sorted: # extract_pmid_groups でソート済み
                if pmid_in_group in self.pmid_to_number_map:
                    citation_numbers_for_group.append(
                        self.pmid_to_number_map[pmid_in_group]
                    )
                else:
                    logging.warning(
                        f"PMID {pmid_in_group} が pmid_to_number_map に見つかりません。引用番号リストから除外されます。"
                    )

            # 引用番号をさらにソート（通常は不要だが念のため）し、指定のフォーマットに整形
            # extract_pmid_groups でグループ内のPMIDはソート済みだが、番号自体はソートされていない可能性があるため
            # (実際にはpmid_to_number_mapの番号は昇順なので、pmidソート順＝番号ソート順になるはず)
            # しかし、_format_citation_numbers内部でソートされるので、ここでのソートは必須ではない。
            # sorted_citation_numbers = sorted(list(set(citation_numbers_for_group)))

            formatted_numbers_string = self._format_citation_numbers(
                citation_numbers_for_group # _format_citation_numbers がソートと整形を行う
            )

            # 置換前のテキストを追加 (前のグループの終わりから今のグループの始まりまで)
            new_content_parts.append(
                markdown_content[last_processed_end:group_start_pos]
            )

            if formatted_numbers_string:
                # citation_format を使って最終的な引用文字列を生成
                final_citation_string = self.citation_format.replace(
                    "{number}", formatted_numbers_string
                )
                new_content_parts.append(final_citation_string)
            else:
                # フォーマットされた番号文字列がない場合（例：PMIDがマップになかった等）
                # 元のPMIDプレースホルダー群をそのまま残す
                new_content_parts.append(
                    markdown_content[group_start_pos:group_end_pos]
                )
                logging.warning(
                    f"PMIDグループ {group_pmids_sorted} の引用番号が生成できなかったため、元のテキストを保持します。"
                )

            last_processed_end = group_end_pos

        # 残りのテキストを追加
        new_content_parts.append(markdown_content[last_processed_end:])

        modified_content = "".join(new_content_parts)
        logging.info("本文中の引用をグループ対応・スパン情報利用で置換しました。")
        return modified_content

    def process_file(self, input_filepath: Path, output_filepath: Path) -> bool:
        """Markdown ファイルを処理して引用を置換し、References を追加する"""
        logging.info(f"処理開始: {input_filepath}")
        try:
            # input_filepath は Path オブジェクトなので、そのまま open に渡せる
            with open(input_filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            logging.error(f"入力ファイルが見つかりません - {input_filepath}")
            return False
        except Exception as e:
            logging.error(f"ファイル読み込み中にエラーが発生しました - {e}")
            return False

        # extract_pmid_groups を呼び出して PMID グループと pmid_to_number_map を準備
        # この時点で self.pmid_to_number_map が設定される
        # pmid_groups_with_spans には (sorted_pmid_list, (start_offset, end_offset)) のリストが返る
        pmid_groups_with_spans = self.extract_pmid_groups(content)

        # fetch_pubmed_details に渡すためのユニークなPMIDリストを取得
        # pmid_to_number_map のキーがそのリストになる
        pmids_for_fetching = list(self.pmid_to_number_map.keys())

        if not pmids_for_fetching:
            logging.warning(
                "PMID 形式の引用が見つからなかったか、処理できるPMIDがありません。処理を終了します。"
            )
            try:
                if input_filepath != output_filepath:
                    import shutil

                    shutil.copy2(input_filepath, output_filepath)
                    logging.info(
                        f"PMIDが見つからなかったため、入力ファイルをそのまま出力しました: {output_filepath}"
                    )
                else:
                    logging.info(
                        "PMIDが見つからず、入力ファイルと出力ファイルが同じため、変更はありません。"
                    )
                return True
            except Exception as e_copy:
                logging.error(f"入力ファイルのコピー中にエラー: {e_copy}")
                return False

        self.fetch_pubmed_details(pmids_for_fetching)
        has_valid_details = any(
            "error" not in detail for detail in self.pubmed_details.values()
        )
        if not has_valid_details and self.pubmed_details:
            logging.warning("PubMed から有効な論文情報を取得できませんでした。")

        # replace_citations に pmid_groups_with_spans を渡す
        modified_content = self.replace_citations(content, pmid_groups_with_spans)

        header_level = self.detect_header_level(content)
        dynamic_references_header = "#" * header_level + " References"

        references_section = self.create_references_section(dynamic_references_header)

        modified_content_no_refs = re.sub(
            r"(\\n\\n#+\\s+References\\s*\\n.*|\\A#+\\s+References\\s*\\n.*)",
            "",
            modified_content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        final_content = modified_content_no_refs.rstrip() + references_section
        try:
            with open(output_filepath, "w", encoding="utf-8") as f:
                f.write(final_content)
            logging.info(f"処理結果をファイルに保存しました: {output_filepath}")
            return True
        except Exception as e:
            logging.error(f"ファイル書き込み中にエラーが発生しました - {e}")
            return False


# --- メイン処理 ---
def main():
    parser = argparse.ArgumentParser(
        description=textwrap.dedent(
            """
            Markdown ファイル内の PubMed 引用を処理し、References リストを生成・置換します。
            PMID は `[pmid 12345](...)` または `[pm 12345](...)` の形式で記述します。
            例: `[pmid 12345](...)`, `[pm 67890](...)`, `[pmid 123] (...) [pmid 456] (...)`
            """
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="処理する Markdown ファイルのパス。指定しない場合はダイアログで選択します。",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        help="出力ファイルパス。指定しない場合は入力ファイル名に `_cited` を付加します。",
    )
    parser.add_argument(
        "--pmid-regex",
        default=PubMedProcessor.DEFAULT_PMID_REGEX_PATTERN,
        help=f"PMID を抽出する正規表現パターン。\nデフォルト: `{PubMedProcessor.DEFAULT_PMID_REGEX_PATTERN}`",
    )
    parser.add_argument(
        "--author-threshold",
        type=int,
        default=PubMedProcessor.DEFAULT_AUTHOR_THRESHOLD,
        help="表示する著者名の最大数。0 で全員表示。\nデフォルト: {PubMedProcessor.DEFAULT_AUTHOR_THRESHOLD}",
    )
    parser.add_argument(
        "--citation-format",
        default=PubMedProcessor.DEFAULT_CITATION_FORMAT,
        help=f"本文中の引用形式。{{number}} で参照番号。\nデフォルト: `{PubMedProcessor.DEFAULT_CITATION_FORMAT}`",
    )
    parser.add_argument(
        "--ref-item-format",
        default=PubMedProcessor.DEFAULT_REFERENCE_ITEM_FORMAT,
        help=textwrap.dedent(
            f"""References の各項目形式。プレースホルダー:
            {{number}}, {{authors}}, {{title}}, {{journal}}, {{year}},
            {{volume}}, {{issue}}, {{pages}}, {{doi}}, {{pmid}}
            デフォルト: `{PubMedProcessor.DEFAULT_REFERENCE_ITEM_FORMAT}`"""
        ),
    )
    parser.add_argument(
        "--api-delay",
        type=float,
        default=PubMedProcessor.DEFAULT_API_REQUEST_DELAY,
        help=f"PubMed API へのリクエスト間隔 (秒)。\nデフォルト: {PubMedProcessor.DEFAULT_API_REQUEST_DELAY}",
    )
    parser.add_argument(
        "--references-header",
        default="References",
        help='References セクションのヘッダー名。\nデフォルト: "References"',
    )
    parser.add_argument(
        "--cache-file",
        default=None, # デフォルトは None とし、Processor 側で処理
        help=f"キャッシュファイルのパスまたはキャッシュを保存するディレクトリ。\n指定しない場合、OSの一時フォルダに `{PubMedProcessor.DEFAULT_CACHE_FILENAME}` が作成されます。\nディレクトリを指定した場合、その中に `{PubMedProcessor.DEFAULT_CACHE_FILENAME}` が作成されます。",
    )
    parser.add_argument(
        "--use-cache",
        type=lambda x: (str(x).lower() == 'true'), # 文字列 'true'/'false' を bool に変換
        default=True,
        help="キャッシュを使用するかどうか (true/false)。\nデフォルト: true",
    )
    parser.add_argument(
        "--no-cache", # --use-cache=false のショートカット
        action="store_false", # これが指定されると use_cache が False になる
        dest="use_cache", # use_cache 引数を上書き
        help="キャッシュを使用しない (--use-cache=false と同等)。",
    )

    args = parser.parse_args()

    input_filepath_str = args.input_file
    if not input_filepath_str:
        logging.info("入力ファイルが指定されていません。ファイル選択ダイアログを開きます。")
        input_filepath_str = ask_for_file()
        if not input_filepath_str:
            return  # ファイル選択がキャンセルされた場合

    input_file = Path(input_filepath_str)  # Path オブジェクトに変換

    if not input_file.is_file():
        logging.error(f"入力ファイルが見つかりません: {input_file}")
        return

    output_file_str = args.output_file
    if not output_file_str:
        output_file = input_file.with_name(f"{input_file.stem}_cited{input_file.suffix}")
    else:
        output_file = Path(output_file_str) # Path オブジェクトに変換
        # 出力ファイルパスがディレクトリを指している場合、入力ファイル名を使ってファイル名を生成
        if output_file.is_dir():
            logging.info(f"出力パス {output_file} はディレクトリです。入力ファイル名を使用してファイルを作成します。")
            output_file = output_file / f"{input_file.stem}_cited{input_file.suffix}"

        # 出力ディレクトリが存在しない場合は作成
        output_dir = output_file.parent
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                logging.info(f"出力ディレクトリを作成しました: {output_dir}")
            except Exception as e:
                logging.error(f"出力ディレクトリの作成に失敗しました: {output_dir} - {e}")
                return # ディレクトリ作成失敗時は処理を中断


    processor = PubMedProcessor(
        pmid_regex_pattern=args.pmid_regex,
        author_threshold=args.author_threshold,
        citation_format=args.citation_format,
        ref_item_format=args.ref_item_format,
        api_delay=args.api_delay,
        cache_file=args.cache_file, # Path or str or None
        use_cache=args.use_cache,   # bool
    )
    # process_file には Path オブジェクトを渡す
    success = processor.process_file(input_file, output_file)
    if (success):
        logging.info("処理が正常に完了しました。")
    else:
        logging.error("処理中にエラーが発生しました。")


if __name__ == "__main__":
    main()
