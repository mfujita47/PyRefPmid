#!/usr/bin/env python3
"""
PyRefPmid - Markdown PubMed Referencer

Description:
    Markdown ファイル内に記述された PubMed ID (PMID) を検出し、
    PubMed API を利用して論文情報を取得し、整形された参考文献リストを生成・追記または更新します。

Usage:
    python PyRefPmid.py [input_file] [options]

Requirements:
    requests
"""
from __future__ import annotations

__version__ = "1.3.0"
__author__ = "mfujita47 (Mitsugu Fujita)"

import argparse
import json
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

import requests

# =============================================================================
# Default Settings & Constants
# =============================================================================

DEFAULT_SETTINGS = {
    "pmid_regex_pattern": r"(?i)\[pm(?:id)?:?\s*(\d+)\](?:\([^)]*\))?",
    "author_threshold": 0,
    "citation_format": "({number})",
    "author_name_format": "{last} {initials}",
    "reference_item_format": "{number}. {authors}. {title} {journal} {year};{volume}:{pages}. doi: {doi}. [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)",
    "references_header": "References",
    "api_base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    "api_request_delay": 0.4,
    "api_key": None,
    "api_timeout": 10.0,
    "use_cache": True,
}

# =============================================================================
# Type Aliases
# =============================================================================
PMID: TypeAlias = str
MetaDict: TypeAlias = dict[str, Any]


# =============================================================================
# Data Models
# =============================================================================


@dataclass(frozen=True)
class GlobalSettings:
    """グローバル設定"""

    pmid_regex_pattern: str = DEFAULT_SETTINGS["pmid_regex_pattern"]  # type: ignore
    author_threshold: int = DEFAULT_SETTINGS["author_threshold"]  # type: ignore
    citation_format: str = DEFAULT_SETTINGS["citation_format"]  # type: ignore
    reference_item_format: str = DEFAULT_SETTINGS["reference_item_format"]  # type: ignore
    author_name_format: str = DEFAULT_SETTINGS["author_name_format"] # type: ignore
    references_header: str = DEFAULT_SETTINGS["references_header"]  # type: ignore
    api_base_url: str = DEFAULT_SETTINGS["api_base_url"]  # type: ignore
    api_request_delay: float = DEFAULT_SETTINGS["api_request_delay"]  # type: ignore
    api_key: str | None = DEFAULT_SETTINGS["api_key"]  # type: ignore
    api_timeout: float = DEFAULT_SETTINGS["api_timeout"]  # type: ignore
    use_cache: bool = DEFAULT_SETTINGS["use_cache"]  # type: ignore


@dataclass
class ArticleMetadata:
    """論文のメタデータ"""

    pmid: PMID
    title: str = "N/A"
    authors_list: list[str] = field(default_factory=list)
    journal: str = "N/A"
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None

    def to_dict(self) -> MetaDict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: MetaDict) -> ArticleMetadata:
        """辞書からインスタンスを生成（不要なキーは無視）"""
        # クラス定義にあるフィールドのみを抽出
        known_keys = cls.__annotations__.keys()
        filtered_data = {k: v for k, v in data.items() if k in known_keys}

        # authors_list の型チェック兼変換
        if "authors_list" in filtered_data:
            if not isinstance(filtered_data["authors_list"], list):
                filtered_data["authors_list"] = []

        return cls(**filtered_data)


# =============================================================================
# Core Components
# =============================================================================


class PubMedClient:
    """PubMed API との通信を担当"""

    def __init__(self, settings: GlobalSettings):
        self.settings = settings
        # APIキーがある場合は遅延を短縮
        self.delay = 0.1 if self.settings.api_key else self.settings.api_request_delay

    def fetch_details(
        self, pmids: list[PMID]
    ) -> tuple[dict[PMID, ArticleMetadata], list[PMID]]:
        """指定された PMID リストの詳細を PubMed API から取得"""
        if not pmids:
            return {}, []

        chunk_size = 100
        api_details: dict[PMID, ArticleMetadata] = {}
        api_not_found: list[PMID] = []

        print(f"Fetching {len(pmids)} articles from PubMed API...")

        for i in range(0, len(pmids), chunk_size):
            chunk = pmids[i : i + chunk_size]
            pmid_string = ",".join(chunk)
            url = f"{self.settings.api_base_url}esummary.fcgi?db=pubmed&id={pmid_string}&retmode=json"
            if self.settings.api_key:
                url += f"&api_key={self.settings.api_key}"

            # Simple progress log
            # print(f"  Requesting chunk {i//chunk_size + 1}...")

            try:
                response = requests.get(url, timeout=self.settings.api_timeout)
                response.raise_for_status()
                data = response.json()
                results = data.get("result")

                if not results or "uids" not in results:
                    api_not_found.extend(chunk)
                    for pmid in chunk:
                        api_details[pmid] = ArticleMetadata(
                            pmid=pmid, error="Not found in API response"
                        )
                    continue

                returned_uids = results.get("uids", [])
                self._process_results(
                    chunk, returned_uids, results, api_details, api_not_found
                )

            except requests.exceptions.RequestException as e:
                print(f"  Error: Connection failed - {e}")
                api_not_found.extend(chunk)
                for pmid in chunk:
                    api_details[pmid] = ArticleMetadata(
                        pmid=pmid, error=f"API connection failed: {e}"
                    )
            except Exception as e:
                print(f"  Error: Unexpected error - {e}")
                api_not_found.extend(chunk)
                for pmid in chunk:
                    api_details[pmid] = ArticleMetadata(
                        pmid=pmid, error=f"Unexpected error: {e}"
                    )

            if i + chunk_size < len(pmids):
                time.sleep(self.delay)

        return api_details, list(set(api_not_found))

    def _process_results(
        self,
        requested_pmids: list[PMID],
        returned_uids: list[str],
        results: dict,
        api_details: dict[PMID, ArticleMetadata],
        api_not_found: list[PMID],
    ):
        """APIの結果を解析"""
        requested_set = set(requested_pmids)
        returned_set = set(returned_uids)
        missing = list(requested_set - returned_set)

        if missing:
            api_not_found.extend(missing)
            for pmid in missing:
                api_details[pmid] = ArticleMetadata(
                    pmid=pmid, error="Not found in API response"
                )

        for pmid in returned_uids:
            if pmid not in results:
                continue

            entry = results[pmid]
            if "error" in entry:
                if pmid not in api_not_found:
                    api_not_found.append(pmid)
                api_details[pmid] = ArticleMetadata(pmid=pmid, error=entry["error"])
                continue

            api_details[pmid] = self._extract_entry_data(pmid, entry)

    def _extract_entry_data(self, pmid: PMID, entry: dict) -> ArticleMetadata:
        """個々のエントリからデータを抽出"""
        authors_list = entry.get("authors", [])
        author_names = [a.get("name", "N/A") for a in authors_list]

        articleids = entry.get("articleids", [])
        doi = next(
            (aid.get("value", "") for aid in articleids if aid.get("idtype") == "doi"),
            "",
        )
        if not doi and entry.get("elocationid", "").startswith("doi:"):
            doi = entry.get("elocationid", "").replace("doi: ", "")

        return ArticleMetadata(
            pmid=pmid,
            title=entry.get("title", "N/A"),
            authors_list=author_names,
            year=entry.get("pubdate", "").split(" ")[0],
            journal=entry.get("source", "N/A"),
            volume=str(entry.get("volume", "")),
            issue=str(entry.get("issue", "")),
            pages=str(entry.get("pages", "")),
            doi=doi,
        )


class CacheManager:
    """キャッシュ管理"""

    def __init__(self, settings: GlobalSettings, cache_path: Path | None = None):
        self.settings = settings
        self.cache_data: dict[PMID, ArticleMetadata] = {}

        if not self.settings.use_cache:
            self.cache_file = None
            return

        # 優先順位:
        # 1. コンストラクタで渡された cache_path (絶対パス指定など)
        # 2. Settings のデフォルト (処理としては呼び出し側で解決して渡す形に変更)

        if cache_path:
            if cache_path.is_dir():
                self.cache_file = cache_path / self.settings.cache_filename
            else:
                # 渡されたのがファイルパスならそのまま使う（拡張子チェックなどは緩く）
                self.cache_file = cache_path
        else:
            # フォールバック（通常は起きないように呼び出し側で制御するが、念のため一時フォルダ）
            self.cache_file = Path(tempfile.gettempdir()) / "pyrefpmid_cache.json"

        self._load()

    def _load(self):
        """キャッシュ読み込み"""
        if not self.cache_file or not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            for pmid, item in raw_data.items():
                try:
                    meta = ArticleMetadata.from_dict(item)
                    self.cache_data[pmid] = meta
                except Exception:
                    pass
        except Exception as e:
            print(f"Warning: Cache load error: {e}")
            self.cache_data = {}

    def save(self):
        """キャッシュ保存"""
        if not self.settings.use_cache or not self.cache_file:
            return

        try:
            if not self.cache_file.parent.exists():
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            serializable_data = {
                pmid: meta.to_dict() for pmid, meta in self.cache_data.items()
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(serializable_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Cache save error: {e}")

    def get_details(
        self, pmids: list[PMID]
    ) -> tuple[dict[PMID, ArticleMetadata], list[PMID]]:
        """キャッシュから取得"""
        if not self.settings.use_cache:
            return {}, list(pmids)

        found = {}
        not_found = []

        for pmid in pmids:
            item = self.cache_data.get(pmid)
            if item and item.is_valid:
                found[pmid] = item
            else:
                not_found.append(pmid)

        return found, not_found

    def update(self, new_details: dict[PMID, ArticleMetadata]):
        """キャッシュ更新"""
        if self.settings.use_cache:
            self.cache_data.update(new_details)
            self.save()


class CitationParser:
    """テキスト解析"""

    def __init__(self, settings: GlobalSettings):
        self.settings = settings
        self.pmid_regex = re.compile(
            self.settings.pmid_regex_pattern, flags=re.IGNORECASE
        )
        self.header_regex = re.compile(
            r"^(#+)\s+(Introduction|Methods|Results|Discussion|Conclusion|Background|Case Report|Abstract|はじめに|方法|結果|考察|結論|背景|症例報告|要旨)",
            re.MULTILINE | re.IGNORECASE,
        )
        escaped_header = re.escape(self.settings.references_header)
        self.remove_refs_regex = re.compile(
            rf"(?m)^#+\s+{escaped_header}\s*\n[\s\S]*?(?=\n#+\s+|\Z)",
            re.IGNORECASE,
        )

    def extract_pmids(
        self, content: str
    ) -> tuple[list[tuple[list[PMID], tuple[int, int]]], dict[PMID, int]]:
        """PMIDを抽出し、グループと出現順マップを返す"""
        matches = list(self.pmid_regex.finditer(content))
        if not matches:
            return [], {}

        pmid_groups = []
        raw_pmids_in_order = []
        current_group_pmids = []
        current_group_start = -1
        current_group_end = 0

        for match in matches:
            pmid = match.group(1)
            start, end = match.span()

            if not current_group_pmids:
                current_group_pmids.append(pmid)
                current_group_start = start
                current_group_end = end
            else:
                inter_text = content[current_group_end:start]
                if not inter_text.strip():
                    current_group_pmids.append(pmid)
                    current_group_end = end
                else:
                    self._finalize_group(
                        pmid_groups,
                        raw_pmids_in_order,
                        current_group_pmids,
                        current_group_start,
                        current_group_end,
                    )
                    current_group_pmids = [pmid]
                    current_group_start = start
                    current_group_end = end

        if current_group_pmids:
            self._finalize_group(
                pmid_groups,
                raw_pmids_in_order,
                current_group_pmids,
                current_group_start,
                current_group_end,
            )

        unique_pmids = list(dict.fromkeys(raw_pmids_in_order))
        pmid_map = {pmid: i + 1 for i, pmid in enumerate(unique_pmids)}

        return pmid_groups, pmid_map

    def _finalize_group(self, groups, raw_list, current_pmids, start, end):
        sorted_pmids = sorted(current_pmids, key=int)
        groups.append((sorted_pmids, (start, end)))
        raw_list.extend(sorted_pmids)

    def detect_header_level(self, content: str) -> int:
        match = self.header_regex.search(content)
        return len(match.group(1)) if match else 2

    def find_reference_section(self, content: str) -> re.Match | None:
        return self.remove_refs_regex.search(content)


class ReferenceFormatter:
    """整形"""

    def __init__(self, settings: GlobalSettings):
        self.settings = settings

    def _parse_name(self, raw_name: str) -> dict[str, str]:
        """PubMed形式の名前(Surname Initials)を解析して辞書を返す"""
        # デフォルト値
        data = {
            "name": raw_name,
            "last": raw_name,
            "initials": "",
        }

        # 単純な空白分割 (Surname Initials)
        parts = raw_name.rsplit(" ", 1)
        if len(parts) == 2:
            # 2つに分かれた場合、後ろがイニシャル(大文字のみ)か確認
            surname, initials = parts
            # シンプルなヒューリスティック: Initialsは大文字のみで構成されることが多い
            # あるいは "Jr" などが含まれるとややこしいが、PubMed APIは基本 "Surname AB"
            if initials.isupper() and len(initials) <= 3:
                data["last"] = surname
                data["initials"] = initials

        return data

    def _format_single_author(self, raw_name: str) -> str:
        """1人の著者名をフォーマットに従って整形"""
        if self.settings.author_name_format == "{name}":
            return raw_name

        data = self._parse_name(raw_name)
        try:
            return self.settings.author_name_format.format(**data)
        except Exception:
            # フォーマットエラー時は生データを返す
            return raw_name

    def _format_authors(self, authors_list: list[str]) -> str:
        # まず個々の著者を整形
        formatted_authors = [self._format_single_author(a) for a in authors_list]

        thresh = self.settings.author_threshold
        if thresh > 0 and len(formatted_authors) > thresh:
            return ", ".join(formatted_authors[:thresh]) + ", et al"
        return ", ".join(formatted_authors)

    def _format_ranges(self, numbers: list[int]) -> str:
        if not numbers:
            return ""
        numbers = sorted(set(numbers))
        ranges = []
        start = end = numbers[0]

        for n in numbers[1:]:
            if n == end + 1:
                end = n
            else:
                ranges.append(
                    f"{start}-{end}" if end > start + 1 else (
                        f"{start},{end}" if end == start + 1 else str(start)
                    )
                )
                start = end = n
        ranges.append(
            f"{start}-{end}" if end > start + 1 else (
                f"{start},{end}" if end == start + 1 else str(start)
            )
        )
        return ",".join(ranges)

    def replace_citations(
        self,
        content: str,
        pmid_groups: list[tuple[list[PMID], tuple[int, int]]],
        pmid_map: dict[PMID, int],
    ) -> str:
        new_parts = []
        last_end = 0

        for group_pmids, (start, end) in pmid_groups:
            nums = [pmid_map[p] for p in group_pmids if p in pmid_map]
            formatted_nums = self._format_ranges(nums)

            new_parts.append(content[last_end:start])
            if formatted_nums:
                new_parts.append(
                    self.settings.citation_format.replace("{number}", formatted_nums)
                )
            else:
                new_parts.append(content[start:end])
            last_end = end

        new_parts.append(content[last_end:])
        return "".join(new_parts)

    def create_section(
        self,
        pmid_map: dict[PMID, int],
        details_map: dict[PMID, ArticleMetadata],
        header_level: int,
    ) -> str:
        if not details_map:
            return ""

        items = []
        for pmid, number in pmid_map.items():
            meta = details_map.get(pmid)
            if meta and meta.is_valid:
                d = meta.to_dict()
                d["authors"] = self._format_authors(meta.authors_list)
                try:
                    formatted_item = self.settings.reference_item_format.format(number=number, **d)
                    # 自動クリーニング: 二重ドットを防ぐ
                    formatted_item = formatted_item.replace("..", ".")
                    items.append(formatted_item)
                except Exception:
                    items.append(f"{number}. [PMID {pmid}] - Format Error")
            else:
                reason = meta.error if meta else "Load Error"
                items.append(f"{number}. [PMID {pmid}] - Get Error ({reason})")

        if not items:
            return ""

        header = "#" * header_level + " " + self.settings.references_header
        return f"{header}\n\n" + "\n".join(items)


# =============================================================================
# Builder
# =============================================================================


class ReferenceBuilder:
    """メイン処理ビルダー"""

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        settings: GlobalSettings,
        cache_path: Path | None = None,
    ):
        self.input_path = input_path
        self.output_path = output_path
        self.settings = settings

        # Components
        self.client = PubMedClient(self.settings)
        # cache_path が None の場合は CacheManager 側で一時フォルダなどが使われるが、
        # main 側で極力 input_path ベースのパスを渡すようにする
        self.cache = CacheManager(self.settings, cache_path)
        self.parser = CitationParser(self.settings)
        self.formatter = ReferenceFormatter(self.settings)

    def build(self) -> bool:
        """処理実行"""
        print(f"Processing: {self.input_path}")

        try:
            content = self.input_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading file: {e}")
            return False

        # 1. コンテンツの分割（既存Referencesを除外して解析するため）
        pre_content, post_content, insertion_mode = self._split_content(content)

        # 解析対象は本文全体 (Referencesセクションを除く)
        scan_target = pre_content + post_content

        # 2. 解析
        pmid_groups, pmid_map = self.parser.extract_pmids(scan_target)
        if not pmid_map:
            print("No PMIDs found in the document.")
            self._copy_if_needed()
            return True

        # 3. 取得 (Cache -> API)
        pmids = list(pmid_map.keys())
        cached_details, missing = self.cache.get_details(pmids)
        api_details, not_found = self.client.fetch_details(missing)

        final_details = {**cached_details, **api_details}
        if api_details:
            self.cache.update(api_details)

        # 4. 置換 (Pre と Post を個別に処理してインデックスずれを防ぐ)
        # extract_pmids は scan_target 全体のオフセットを返すが、
        # pre_content の長さを使えば post_content 用のグループも特定可能。
        # ここではシンプルに ReferenceFormatter を再利用するため、個別に置換を行う。
        # ただし pmid_map (番号) は共有する。

        # pre/post それぞれで再度グループ抽出を行うのは非効率だが、
        # 正確性を期すなら文字列置換は慎重に行う必要がある。
        # formatter.replace_citations は「テキスト全部」と「その中のグループ位置」を受け取る設計。
        # scan_target に対する groups は既にあるので、それを split ポイントで分割して適用する。

        split_point = len(pre_content)
        pre_groups = []
        post_groups = []

        for pmid_list, span in pmid_groups:
            start, end = span
            if end <= split_point:
                pre_groups.append((pmid_list, span))
            elif start >= split_point:
                # Post側のオフセットは調整が必要
                new_span = (start - split_point, end - split_point)
                post_groups.append((pmid_list, new_span))
            else:
                # 境界を跨ぐケース（まずあり得ないが、あれば Pre に寄せるなどの処理）
                # ここでは安全のため Pre 扱いにする（実質分割点で切れているはず）
                pre_groups.append((pmid_list, span))

        new_pre = self.formatter.replace_citations(pre_content, pre_groups, pmid_map)
        new_post = self.formatter.replace_citations(post_content, post_groups, pmid_map)

        # 5. セクション生成
        header_level = self.parser.detect_header_level(scan_target)
        ref_section = self.formatter.create_section(
            pmid_map, final_details, header_level
        )

        # 6. 結合
        if ref_section:
            if insertion_mode == "append":
                # 末尾に追加（間に改行を入れる）
                final_content = new_pre.rstrip() + "\n\n" + ref_section + "\n" + new_post
            else:
                # 既存置換 or マーカー置換（Pre + Refs + Post）
                # 文脈に合わせて改行を調整
                final_content = new_pre + ref_section + "\n" + new_post
        else:
            # 参考文献なし（PMIDはあるがデータ取得失敗など？通常ここには来ない）
            final_content = new_pre + new_post

        # 7. 保存
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(final_content, encoding="utf-8")
            print(f"✓ Saved to: {self.output_path}")
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
            return False

    def _split_content(self, content: str) -> tuple[str, str, str]:
        """
        コンテンツを (Pre, Post, Mode) に分割する。
        既存の References セクションを削除・除外して、再生成位置を特定するため。
        Mode: "append" (末尾追加), "insert" (中間挿入/置換)
        """
        # 1. マーカー検索 (<!-- REFERENCES --> 等) - 将来拡張用だが今回は既存ヘッダー優先

        # 2. 既存 References セクション検索
        match = self.parser.find_reference_section(content)
        if match:
            # 見つかった場合: その部分を除去して Pre/Post に分ける
            pre = content[: match.start()]
            post = content[match.end() :]
            return pre, post, "insert"

        # 3. 見つからない場合: 全体を Pre とし、Post は空、Mode は Append
        return content, "", "append"

    def _copy_if_needed(self):
        if self.input_path != self.output_path:
            try:
                self.output_path.write_text(
                    self.input_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
            except Exception:
                pass


# =============================================================================
# CLI & Entry Point
# =============================================================================


def _select_file_gui() -> Path | None:
    """GUIファイル選択"""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    filepath = filedialog.askopenfilename(
        title="Select Markdown File",
        filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
    )
    root.destroy()
    return Path(filepath) if filepath else None


def _select_input_file() -> Path | None:
    """入力ファイルをスマートに選択"""
    cwd = Path.cwd()
    # 候補取得（_cited.md は除外すると親切かもしれないが、あえて含めるか、あるいは除外するか。
    # ここではシンプルにすべての .md を対象とするが、自分自身(出力済みファイル)を誤って処理しないように注意）
    candidates = list(cwd.glob("*.md"))

    # 除外ロジック: 明らかに自動生成されたファイル (_cited.md) を優先度下げるなどが可能だが、
    # ユーザーがそれを再処理したい場合もあるので、とりあえず全てリストアップする。

    if len(candidates) == 0:
        return _select_file_gui()

    if len(candidates) == 1:
        target = candidates[0]
        print(f"Auto-selected file: {target.name}")
        return target

    # 複数候補がある場合
    if sys.stdin and sys.stdin.isatty():
        print("Multiple Markdown files found:")
        for i, f in enumerate(candidates, 1):
            print(f"  {i}. {f.name}")
        print("  0. Open File Dialog (GUI)")

        while True:
            try:
                choice = input("Select number: ")
                if not choice: continue
                if choice == "0":
                    return _select_file_gui()
                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(candidates):
                        target = candidates[idx - 1]
                        print(f"Selected: {target.name}")
                        return target
            except (KeyboardInterrupt, EOFError):
                return None
            print("Invalid selection. Try again.")
    else:
        # ターミナルでない場合はGUIへフォールバック
        return _select_file_gui()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PyRefPmid - Automated PubMed Reference Generator",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("input_file", nargs="?", help="Input Markdown file path")
    parser.add_argument("-o", "--output-file", help="Output file path")

    # Settings overrides
    parser.add_argument("--pmid-regex", default=None)
    parser.add_argument("--author-threshold", type=int, default=None)
    parser.add_argument("--citation-format", default=None)
    parser.add_argument("--ref-item-format", default=None)
    parser.add_argument("--author-name-format", default=None, help="Format for author names (e.g. '{last}, {initials_dotted}')")
    parser.add_argument("--api-delay", type=float, default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--references-header", default=None)
    parser.add_argument("--cache-file", default=None)
    parser.add_argument(
        "--no-cache", action="store_true", help="Disable caching"
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Input handling
    input_str = args.input_file
    if input_str:
        input_path = Path(input_str)
    else:
        input_path = _select_input_file()

    if not input_path:
        print("No input file selected.")
        return 0

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1

    # Output handling
    if args.output_file:
        output_path = Path(args.output_file)
        if output_path.is_dir():
            output_path = output_path / f"{input_path.stem}_cited{input_path.suffix}"
    else:
        output_path = input_path.with_name(f"{input_path.stem}_cited{input_path.suffix}")

    # Build Settings
    # Load defaults
    s = DEFAULT_SETTINGS.copy()

    # Update from args if present
    if args.pmid_regex: s["pmid_regex_pattern"] = args.pmid_regex
    if args.author_threshold is not None: s["author_threshold"] = args.author_threshold
    if args.citation_format: s["citation_format"] = args.citation_format
    if args.ref_item_format: s["reference_item_format"] = args.ref_item_format
    if args.author_name_format: s["author_name_format"] = args.author_name_format
    if args.api_delay is not None: s["api_request_delay"] = args.api_delay
    if args.api_key: s["api_key"] = args.api_key
    if args.references_header: s["references_header"] = args.references_header
    if args.no_cache: s["use_cache"] = False

    settings = GlobalSettings(
        pmid_regex_pattern=str(s["pmid_regex_pattern"]),
        author_threshold=int(s["author_threshold"]),
        citation_format=str(s["citation_format"]),
        reference_item_format=str(s["reference_item_format"]),
        author_name_format=str(s["author_name_format"]),
        references_header=str(s["references_header"]),
        api_base_url=str(s["api_base_url"]),
        api_request_delay=float(s["api_request_delay"]),
        api_key=str(s["api_key"]) if s["api_key"] else None,
        api_timeout=float(s["api_timeout"]),
        use_cache=bool(s["use_cache"]),
    )

    # Cache Path Determination
    # デフォルト: 入力ファイルと同じディレクトリに <入力ファイル名>.json として保存
    # ユーザー指定(--cache-file)があればそれを使用
    if args.cache_file:
        cache_path = Path(args.cache_file)
    else:
        # cache_filename 設定はデフォルト値として持っているが、
        # ここでは入力ファイル名に連動させるため、設定値ではなく動的に生成する
        cache_path = input_path.with_suffix(".json")

    # Run Builder
    print("PyRefPmid v" + __version__)
    builder = ReferenceBuilder(input_path, output_path, settings, cache_path)
    success = builder.build()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
