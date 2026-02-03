#!/usr/bin/env python3
"""
PyRefPmid - Markdown PubMed Referencer (Hybrid)

Description:
    Markdown ファイル内に記述された PubMed ID (PMID) を検出し、
    PubMed API を利用して論文情報を取得し、整形された参考文献リストを生成・追記または更新します。

Usage:
    python PyRefPmid.py [input_file] [options]

Requirements:
    requests
"""
from __future__ import annotations

__version__ = "2.2.0"
__author__ = "mfujita47 (Mitsugu Fujita)"

import argparse
import concurrent.futures
import json
import re
import sys
import threading
import time
from dataclasses import MISSING, asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

# 外部ライブラリチェック
try:
    import requests
except ImportError:
    print("Error: 'requests' library is missing. Please install it via 'pip install requests'.")
    sys.exit(1)

# =============================================================================
# Default Settings
# =============================================================================


@dataclass(frozen=True)
class GlobalSettings:
    """グローバル設定"""

    pmid_regex_pattern: str = r"(?i)\[pm(?:id)?:?\s*(\d+)\](?:\([^)]*\))?"
    author_threshold: int = 0
    author_display_count: int = 0  # threshold超過時に表示する著者数 (0 = thresholdと同値)
    citation_format: str = "({number})"
    author_name_format: str = "{last} {initials}"
    reference_item_format: str = "{number}. {authors}. {title} {journal} {year};{volume}({issue}):{pages}. doi: {doi}. [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)"
    references_header: str = "References"
    api_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    api_key: str | None = None
    api_timeout: float = 10.0
    max_workers: int = 5
    use_cache: bool = True


# GlobalSettings から DEFAULT_SETTINGS を自動生成
DEFAULT_SETTINGS: dict[str, Any] = {
    f.name: f.default for f in fields(GlobalSettings) if f.default is not MISSING
}

# =============================================================================
# Type Aliases
# =============================================================================

PMID = str
MetaDict = dict[str, Any]

# =============================================================================
# Data Models
# =============================================================================


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

    @classmethod
    def from_dict(cls, data: MetaDict) -> ArticleMetadata:
        """辞書からインスタンスを生成"""
        known_keys = cls.__annotations__.keys()
        filtered_data = {k: v for k, v in data.items() if k in known_keys}
        if "authors_list" in filtered_data and not isinstance(filtered_data["authors_list"], list):
            filtered_data["authors_list"] = []
        return cls(**filtered_data)


# =============================================================================
# Utilities
# =============================================================================


class RateLimiter:
    """APIレート制限を管理するスレッドセーフなクラス"""

    def __init__(self, calls_per_second: float):
        self.interval = 1.0 / calls_per_second
        self.lock = threading.Lock()
        self.last_call = 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            wait_time = self.interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self.last_call = time.time()


# =============================================================================
# Core Components
# =============================================================================


class PubMedClient:
    """PubMed API クライアント (並列処理対応)"""

    def __init__(self, settings: GlobalSettings):
        self.settings = settings
        # APIキーありなら10req/sec, なしなら3req/sec (安全マージン)
        limit = 9.0 if settings.api_key else 2.5
        self.limiter = RateLimiter(limit)
        self.session = requests.Session()

    def _fetch_chunk(self, pmids: list[PMID]) -> dict[PMID, ArticleMetadata]:
        """PMIDのリスト(最大50件)を一括取得"""
        if not pmids:
            return {}

        self.limiter.wait()
        pmid_str = ",".join(pmids)
        params = {
            "db": "pubmed",
            "id": pmid_str,
            "retmode": "json",
        }
        if self.settings.api_key:
            params["api_key"] = self.settings.api_key

        results: dict[PMID, ArticleMetadata] = {}
        try:
            resp = self.session.get(
                self.settings.api_base_url,
                params=params,
                timeout=self.settings.api_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            result = data.get("result", {})
            uids = result.get("uids", [])

            for pmid in pmids:
                if pmid in uids:
                    item = result[pmid]
                    if "error" in item:
                        results[pmid] = ArticleMetadata(pmid=pmid, error=item["error"])
                    else:
                        results[pmid] = self._parse_json(pmid, item)
                else:
                    results[pmid] = ArticleMetadata(pmid=pmid, error="Not found")

        except Exception as e:
            print(f"  [API Error] Batch failed: {e}")
            for pmid in pmids:
                results[pmid] = ArticleMetadata(pmid=pmid, error=str(e))

        return results

    def _parse_json(self, pmid: PMID, item: dict) -> ArticleMetadata:
        """JSONレスポンスをArticleMetadataに変換"""
        doi = ""
        for aid in item.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
                break
        elocationid = item.get("elocationid", "")
        if not doi and elocationid.startswith("doi:"):
            doi = elocationid.replace("doi: ", "")

        authors = [a.get("name", "") for a in item.get("authors", []) if "name" in a]

        return ArticleMetadata(
            pmid=pmid,
            title=item.get("title", "N/A"),
            authors_list=authors,
            journal=item.get("source", "N/A"),
            year=item.get("pubdate", "").split()[0] if item.get("pubdate") else "",
            volume=str(item.get("volume", "")),
            issue=str(item.get("issue", "")),
            pages=str(item.get("pages", "")),
            doi=doi,
        )

    def fetch_all(self, pmids: list[PMID]) -> dict[PMID, ArticleMetadata]:
        """並列処理で全PMIDを取得"""
        unique_pmids = list(set(pmids))
        if not unique_pmids:
            return {}

        results: dict[PMID, ArticleMetadata] = {}
        chunk_size = 50
        chunks = [
            unique_pmids[i : i + chunk_size]
            for i in range(0, len(unique_pmids), chunk_size)
        ]

        print(f"Fetching {len(unique_pmids)} articles using {self.settings.max_workers} threads...")

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.settings.max_workers
        ) as executor:
            future_to_chunk = {
                executor.submit(self._fetch_chunk, chunk): chunk for chunk in chunks
            }
            for future in concurrent.futures.as_completed(future_to_chunk):
                try:
                    data = future.result()
                    results.update(data)
                except Exception as e:
                    print(f"  [Thread Error] {e}")

        return results


class CacheManager:
    """ローカルファイルへのキャッシュ管理"""

    def __init__(self, filepath: Path, use_cache: bool = True):
        self.filepath = filepath
        self.use_cache = use_cache
        self.data: dict[PMID, ArticleMetadata] = {}
        if self.use_cache:
            self._load()

    def _load(self):
        if not self.filepath.exists():
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                raw = json.load(f)
                for k, v in raw.items():
                    self.data[k] = ArticleMetadata.from_dict(v)
        except Exception as e:
            print(f"Warning: Cache load failed ({e}). Starting fresh.")

    def save(self):
        if not self.use_cache:
            return
        try:
            export = {k: asdict(v) for k, v in self.data.items()}
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(export, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Cache save failed ({e})")

    def get_missing(
        self, pmids: list[PMID]
    ) -> tuple[dict[PMID, ArticleMetadata], list[PMID]]:
        if not self.use_cache:
            return {}, list(pmids)
        found = {}
        missing = []
        for pmid in pmids:
            if pmid in self.data and self.data[pmid].is_valid:
                found[pmid] = self.data[pmid]
            else:
                missing.append(pmid)
        return found, missing

    def update(self, new_data: dict[PMID, ArticleMetadata]):
        if self.use_cache:
            self.data.update(new_data)
            self.save()


class CitationParser:
    """テキスト解析"""

    def __init__(self, settings: GlobalSettings):
        self.settings = settings
        self.pmid_regex = re.compile(self.settings.pmid_regex_pattern)
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

        pmid_groups: list[tuple[list[PMID], tuple[int, int]]] = []
        raw_pmids_in_order: list[PMID] = []
        current_group_pmids: list[PMID] = []
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
        data = {
            "name": raw_name,
            "last": raw_name,
            "initials": "",
        }
        parts = raw_name.rsplit(" ", 1)
        if len(parts) == 2:
            surname, initials = parts
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
            return raw_name

    def _format_authors(self, authors_list: list[str]) -> str:
        formatted_authors = [self._format_single_author(a) for a in authors_list]
        thresh = self.settings.author_threshold
        if thresh > 0 and len(formatted_authors) > thresh:
            # display_count が指定されていればその数、なければ threshold と同じ数を表示
            display = self.settings.author_display_count or thresh
            return ", ".join(formatted_authors[:display]) + ", et al"
        return ", ".join(formatted_authors)

    def _format_ranges(self, numbers: list[int]) -> str:
        """連続した番号を範囲形式に圧縮 (例: 1,2,3 -> 1-3)"""
        if not numbers:
            return ""
        numbers = sorted(set(numbers))
        ranges = []
        start = end = numbers[0]

        def append_range():
            if end > start + 1:
                ranges.append(f"{start}-{end}")
            elif end == start + 1:
                ranges.append(f"{start},{end}")
            else:
                ranges.append(str(start))

        for n in numbers[1:]:
            if n == end + 1:
                end = n
            else:
                append_range()
                start = end = n
        append_range()
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
                authors_str = self._format_authors(meta.authors_list)
                try:
                    formatted_item = self.settings.reference_item_format.format(
                        number=number,
                        authors=authors_str,
                        title=meta.title,
                        journal=meta.journal,
                        year=meta.year,
                        volume=meta.volume,
                        issue=meta.issue,
                        pages=meta.pages,
                        doi=meta.doi,
                        pmid=meta.pmid,
                    )
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
# Main Processor
# =============================================================================


class ReferenceBuilder:
    """メイン処理"""

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        settings: GlobalSettings,
        cache_path: Path,
    ):
        self.input_path = input_path
        self.output_path = output_path
        self.settings = settings
        self.client = PubMedClient(self.settings)
        self.cache = CacheManager(cache_path, self.settings.use_cache)
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

        # 1. コンテンツの分割（既存Referencesを除外して解析）
        pre_content, post_content, insertion_mode = self._split_content(content)
        scan_target = pre_content + post_content

        # 2. 解析
        pmid_groups, pmid_map = self.parser.extract_pmids(scan_target)
        if not pmid_map:
            print("No PMIDs found in the document.")
            self._copy_if_needed(content)
            return True

        # 3. 取得 (Cache -> API)
        pmids = list(pmid_map.keys())
        cached_details, missing = self.cache.get_missing(pmids)

        api_details: dict[PMID, ArticleMetadata] = {}
        if missing:
            api_details = self.client.fetch_all(missing)
            self.cache.update(api_details)

        final_details = {**cached_details, **api_details}

        # 4. 置換
        split_point = len(pre_content)
        pre_groups = []
        post_groups = []

        for pmid_list, span in pmid_groups:
            start, end = span
            if end <= split_point:
                pre_groups.append((pmid_list, span))
            elif start >= split_point:
                new_span = (start - split_point, end - split_point)
                post_groups.append((pmid_list, new_span))
            else:
                pre_groups.append((pmid_list, span))

        new_pre = self.formatter.replace_citations(pre_content, pre_groups, pmid_map)
        new_post = self.formatter.replace_citations(post_content, post_groups, pmid_map)

        # 5. セクション生成
        header_level = self.parser.detect_header_level(scan_target)
        ref_section = self.formatter.create_section(pmid_map, final_details, header_level)

        # 6. 結合
        if ref_section:
            if insertion_mode == "append":
                final_content = new_pre.rstrip() + "\n\n" + ref_section + "\n" + new_post
            else:
                final_content = new_pre + ref_section + "\n" + new_post
        else:
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
        """
        match = self.parser.find_reference_section(content)
        if match:
            pre = content[: match.start()]
            post = content[match.end() :]
            return pre, post, "insert"
        return content, "", "append"

    def _copy_if_needed(self, content: str):
        if self.input_path != self.output_path:
            try:
                self.output_path.write_text(content, encoding="utf-8")
            except Exception:
                pass


# =============================================================================
# CLI & Entry Point
# =============================================================================


def _select_file_gui() -> Path | None:
    """GUIファイル選択"""
    try:
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
    except Exception:
        return None


def _select_input_file() -> Path | None:
    """入力ファイル選択"""
    cwd = Path.cwd()
    candidates = list(cwd.glob("*.md"))

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
                if not choice:
                    continue
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
        print("Multiple markdown files found. Opening selector...")
        return _select_file_gui()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PyRefPmid - Hybrid PubMed Reference Generator",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("input_file", nargs="?", help="Input Markdown file path")
    parser.add_argument("-o", "--output-file", help="Output file path")

    # Settings overrides (defaults from DEFAULT_SETTINGS)
    parser.add_argument("--pmid-regex", default=DEFAULT_SETTINGS["pmid_regex_pattern"])
    parser.add_argument("--author-threshold", type=int, default=DEFAULT_SETTINGS["author_threshold"])
    parser.add_argument("--author-display", type=int, default=DEFAULT_SETTINGS["author_display_count"],
                        help="Number of authors to show when exceeding threshold (0 = same as threshold)")
    parser.add_argument("--citation-format", default=DEFAULT_SETTINGS["citation_format"])
    parser.add_argument("--ref-item-format", default=DEFAULT_SETTINGS["reference_item_format"])
    parser.add_argument(
        "--author-name-format",
        default=DEFAULT_SETTINGS["author_name_format"],
        help="Format for author names (e.g. '{last}, {initials}')",
    )
    parser.add_argument("--api-key", default=DEFAULT_SETTINGS["api_key"])
    parser.add_argument("--references-header", default=DEFAULT_SETTINGS["references_header"])
    parser.add_argument("--cache-file", default=None)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_SETTINGS["max_workers"], help="Max parallel threads")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")

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

    # Build Settings - args already contain defaults from argparse
    settings = GlobalSettings(
        pmid_regex_pattern=args.pmid_regex,
        author_threshold=args.author_threshold,
        author_display_count=args.author_display,
        citation_format=args.citation_format,
        reference_item_format=args.ref_item_format,
        author_name_format=args.author_name_format,
        references_header=args.references_header,
        api_key=args.api_key,
        max_workers=args.max_workers,
        use_cache=not args.no_cache,
    )

    # Cache Path Determination
    if args.cache_file:
        cache_path = Path(args.cache_file)
    else:
        cache_path = input_path.with_suffix(".json")

    # Run Builder
    print(f"PyRefPmid v{__version__}")
    builder = ReferenceBuilder(input_path, output_path, settings, cache_path)
    success = builder.build()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
