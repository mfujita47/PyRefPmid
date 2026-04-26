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

__version__ = "3.0.0"
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

try:
    from citeproc import (
        CitationStylesStyle,
        CitationStylesBibliography,
        Citation,
        CitationItem,
        formatter,
    )
    from citeproc.source.json import CiteProcJSON
except ImportError:
    print("Error: 'citeproc-py' library is missing. Please install it via 'pip install citeproc-py'.")
    sys.exit(1)

@dataclass(frozen=True)
class GlobalSettings:

    pmid_regex_pattern: str = r"(?i)\[pm(?:id)?:?\s*(\d+)\](?:\([^)]*\))?"
    csl_style: str = "apa"
    csl_locale: str = "en-US"
    references_header: str = "References"
    api_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    api_key: str | None = "3a88fc215344206ea89f04981d824c4ca608"
    api_timeout: float = 10.0
    max_workers: int = 5
    use_cache: bool = True

# GlobalSettings から DEFAULT_SETTINGS を自動生成
DEFAULT_SETTINGS: dict[str, Any] = {
    f.name: f.default for f in fields(GlobalSettings) if f.default is not MISSING
}

PMID = str
MetaDict = dict[str, Any]

@dataclass
class ArticleMetadata:

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
        known_keys = cls.__annotations__.keys()
        filtered_data = {k: v for k, v in data.items() if k in known_keys}
        if "authors_list" in filtered_data and not isinstance(filtered_data["authors_list"], list):
            filtered_data["authors_list"] = []
        return cls(**filtered_data)

    def to_csl_json(self) -> dict[str, Any]:
        """Convert metadata to CSL-JSON format for citeproc-py."""
        authors = []
        for name in self.authors_list:
            if "," in name:
                parts = [p.strip() for p in name.split(",", 1)]
                authors.append({"family": parts[0], "given": parts[1]})
            else:
                parts = name.rsplit(" ", 1)
                if len(parts) == 2:
                    surname, initials = parts
                    if initials.isupper() and len(initials) <= 3:
                        # Split initials (e.g., "MK" -> "M. K.") for better CSL handling
                        given = " ".join(list(initials))
                        authors.append({"family": surname, "given": given})
                    else:
                        authors.append({"family": name, "given": ""})
                else:
                    authors.append({"family": name, "given": ""})

        csl: dict[str, Any] = {
            "id": self.pmid,
            "type": "article-journal",
            "title": self.title,
            "container-title": self.journal,
            "volume": self.volume,
            "issue": self.issue,
            "page": self.pages,
            "DOI": self.doi,
        }
        if self.year:
            try:
                # Year can be "2023 Oct" or just "2023"
                clean_year = re.search(r"\d{4}", self.year)
                if clean_year:
                    csl["issued"] = {"date-parts": [[int(clean_year.group())]]}
            except (ValueError, AttributeError):
                pass
        if authors:
            csl["author"] = authors
        return csl

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

class CiteprocFormatter:
    """CSL (citeproc-py) を使用した文献フォーマッタ"""

    def __init__(self, settings: GlobalSettings, details_map: dict[PMID, ArticleMetadata]):
        self.settings = settings
        self.details_map = details_map

        # 有効なメタデータのみを CSL-JSON 形式に変換
        csl_data = [
            meta.to_csl_json()
            for meta in details_map.values()
            if meta.is_valid
        ]
        self.bib_source = CiteProcJSON(csl_data)

        # スタイルファイルの探索
        style_name = settings.csl_style
        style_path = self._find_style_file(style_name)

        try:
            self.style = CitationStylesStyle(str(style_path), validate=False)
        except Exception as e:
            print(f"Error loading CSL style '{style_name}': {e}")
            sys.exit(1)

        self.bibliography = CitationStylesBibliography(
            self.style, self.bib_source, formatter.plain
        )

    def _find_style_file(self, style_name: str) -> Path:
        """スタイル名から .csl ファイルを探す"""
        # 1. 直接パス指定
        p = Path(style_name)
        if p.exists() and p.is_file():
            return p
        # 2. .csl 拡張子を付与
        p = Path(f"{style_name}.csl")
        if p.exists():
            return p
        # 3. カレントディレクトリ内の .csl を探す (名前が一致するもの)
        for csl in Path.cwd().glob("*.csl"):
            if csl.stem.lower() == style_name.lower():
                return csl

        # フォールバック: 指定がない場合はエラーにするかデフォルトを探す
        # ここではエラーメッセージを出して終了する
        print(f"Error: CSL style file '{style_name}' or '{style_name}.csl' not found.")
        print("Please provide a valid .csl file or ensure it exists in the current directory.")
        sys.exit(1)

    def replace_citations(
        self,
        content: str,
        pmid_groups: list[tuple[list[PMID], tuple[int, int]]],
    ) -> str:
        """本文中の PMID タグを CSL フォーマットの引用符に置換する"""
        if not pmid_groups:
            return content

        def on_nonexistent_item(item_id):
            print(f"  [Warning] Item {item_id} not found in metadata.")

        # 引用を登録
        registered_citations = []
        for group_pmids, _ in pmid_groups:
            items = [
                CitationItem(pmid)
                for pmid in group_pmids
                if pmid in self.details_map and self.details_map[pmid].is_valid
            ]
            if items:
                cit = Citation(items)
                self.bibliography.register(cit)
                registered_citations.append(cit)
            else:
                registered_citations.append(None)

        # 置換処理
        new_parts = []
        last_end = 0

        for i, (group_pmids, (start, end)) in enumerate(pmid_groups):
            new_parts.append(content[last_end:start])
            cit = registered_citations[i]
            if cit:
                try:
                    formatted = self.bibliography.cite(cit, on_nonexistent_item)
                    new_parts.append(str(formatted))
                except Exception as e:
                    print(f"  [Error] Failed to format citation for {group_pmids}: {e}")
                    new_parts.append(content[start:end])
            else:
                new_parts.append(content[start:end])
            last_end = end

        new_parts.append(content[last_end:])
        return "".join(new_parts)

    def create_section(self, header_level: int) -> str:
        """参考文献リストセクションを生成する"""
        bib_items = []

        # citeproc-py の bibliography() はイテレータを返し、各要素は文字列化可能
        for item in self.bibliography.bibliography():
            s = str(item).strip()
            # 1. IEEEなどで "Nameand Name" のようになる現象への対策
            s = re.sub(r"([^\s,])and\s", r"\1 and ", s)
            # 2. "[1]Author" -> "[1] Author"
            s = re.sub(r"(\[\d+\])([^\s])", r"\1 \2", s)
            # 3. "M.&" or ",&" -> "M. &" or ", &" (APAなど)
            s = re.sub(r"([.,])([&])", r"\1 \2", s)
            # 4. ", ." -> "." (Suffixなどの後の不要なカンマ)
            s = s.replace(", .", ".")
            # 5. 二重ピリオド
            s = s.replace("..", ".")

            bib_items.append(s)

        if not bib_items:
            return ""

        header = "#" * header_level + " " + self.settings.references_header
        # Markdownで確実に改行（段落分け）されるよう \n\n で結合する
        # 末尾にも改行を付与する
        return f"{header}\n\n" + "\n\n".join(bib_items) + "\n"

class ReferenceBuilder:

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

    def build(self) -> bool:
        print(f"Processing: {self.input_path}")

        try:
            content = self.input_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Error reading file: {e}")
            return False

        # 1. Split content
        pre_content, post_content, insertion_mode = self._split_content(content)
        scan_target = pre_content + post_content

        # 2. Parse PMIDs
        pmid_groups, pmid_map = self.parser.extract_pmids(scan_target)
        if not pmid_map:
            print("No PMIDs found in the document.")
            self._copy_if_needed(content)
            return True

        # 3. Fetch Metadata (Cache -> API)
        pmids = list(pmid_map.keys())
        cached_details, missing = self.cache.get_missing(pmids)

        api_details: dict[PMID, ArticleMetadata] = {}
        if missing:
            api_details = self.client.fetch_all(missing)
            self.cache.update(api_details)

        final_details = {**cached_details, **api_details}

        # 4. Initialize Citeproc Formatter
        formatter = CiteprocFormatter(self.settings, final_details)

        # 5. Replace Citations
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

        new_pre = formatter.replace_citations(pre_content, pre_groups)
        new_post = formatter.replace_citations(post_content, post_groups)

        # 6. Create References Section
        header_level = self.parser.detect_header_level(scan_target)
        ref_section = formatter.create_section(header_level)

        # 7. Combine
        if ref_section:
            if insertion_mode == "append":
                final_content = new_pre.rstrip() + "\n\n" + ref_section + "\n" + new_post
            else:
                final_content = new_pre + ref_section + "\n" + new_post
        else:
            final_content = new_pre + new_post

        # 8. Save
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            # OSによらず一貫した改行コード (LF) を使用する
            self.output_path.write_text(final_content, encoding="utf-8", newline="\n")
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
                self.output_path.write_text(content, encoding="utf-8", newline="\n")
            except Exception:
                pass

def _select_file_gui(extension: str, label: str) -> Path | None:
    """GUIファイル選択ダイアログを表示する"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        filepath = filedialog.askopenfilename(
            title=f"Select {label} File",
            filetypes=[(f"{label} files", f"*.{extension}"), ("All files", "*.*")],
        )
        root.destroy()
        return Path(filepath) if filepath else None
    except Exception:
        return None

def _select_file_generic(
    extension: str,
    label: str,
    auto_select: bool = True
) -> Path | None:
    """共通のファイル選択ロジック (CLI/GUI)"""
    cwd = Path.cwd()
    candidates = list(cwd.glob(f"*.{extension}"))

    if not candidates:
        return _select_file_gui(extension, label)

    if auto_select and len(candidates) == 1:
        target = candidates[0]
        print(f"Auto-selected {label}: {target.name}")
        return target

    # 複数候補がある場合または auto_select=False
    if sys.stdin and sys.stdin.isatty():
        print(f"Multiple {label} files found:")
        for i, f in enumerate(candidates, 1):
            print(f"  {i}. {f.name}")
        print("  0. Open File Dialog (GUI)")

        while True:
            try:
                choice = input("Select number: ")
                if not choice:
                    continue
                if choice == "0":
                    return _select_file_gui(extension, label)
                if choice.isdigit():
                    idx = int(choice)
                    if 1 <= idx <= len(candidates):
                        target = candidates[idx - 1]
                        print(f"Selected {label}: {target.name}")
                        return target
            except (KeyboardInterrupt, EOFError):
                return None
            print("Invalid selection. Try again.")
    else:
        return _select_file_gui(extension, label)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PyRefPmid - CSL-based PubMed Reference Generator",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("input_file", nargs="?", help="Input Markdown file path")
    parser.add_argument("-o", "--output-file", help="Output file path")

    parser.add_argument("--pmid-regex", default=DEFAULT_SETTINGS["pmid_regex_pattern"])
    parser.add_argument("--csl-style", default=DEFAULT_SETTINGS["csl_style"],
                        help="CSL style name or path to .csl file (default: apa)")
    parser.add_argument("--csl-locale", default=DEFAULT_SETTINGS["csl_locale"],
                        help="CSL locale (default: en-US)")
    parser.add_argument("--api-key", default=DEFAULT_SETTINGS["api_key"])
    parser.add_argument("--references-header", default=DEFAULT_SETTINGS["references_header"])
    parser.add_argument("--cache-file", default=None)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_SETTINGS["max_workers"], help="Max parallel threads")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")

    return parser.parse_args()

def _download_csl(style_name: str) -> Path | None:
    """指定された CSL スタイルを公式リポジトリからダウンロードする"""
    # 拡張子を除去してベース名を取得
    base_name = style_name.replace(".csl", "").lower()
    target_path = Path(f"{base_name}.csl")

    url = f"https://raw.githubusercontent.com/citation-style-language/styles/master/{base_name}.csl"
    print(f"Style '{base_name}' not found locally. Trying to download from: {url}")
    try:
        import requests
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            print(f"Error: Style '{base_name}' not found in the official CSL repository.")
            return None
        resp.raise_for_status()
        # OS によらず LF で保存
        target_path.write_text(resp.text, encoding="utf-8", newline="\n")
        print(f"✓ Downloaded: {target_path.name}")
        return target_path
    except Exception as e:
        print(f"Error: Failed to download CSL '{base_name}': {e}")
        return None

def main() -> int:
    args = parse_args()

    # Input handling
    input_str = args.input_file
    if input_str:
        input_path = Path(input_str)
    else:
        input_path = _select_file_generic("md", "Markdown")

    if not input_path:
        print("No input file selected.")
        return 0

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        return 1

    # CSL Style handling
    csl_style = args.csl_style
    
    # ローカルにあるか確認 (直接パス, .csl付与, 大文字小文字無視)
    local_path = None
    if Path(csl_style).exists() and Path(csl_style).is_file():
        local_path = Path(csl_style)
    elif Path(f"{csl_style}.csl").exists():
        local_path = Path(f"{csl_style}.csl")
    else:
        for csl in Path.cwd().glob("*.csl"):
            if csl.stem.lower() == csl_style.lower():
                local_path = csl
                break

    if local_path:
        csl_style = str(local_path)
    else:
        # ローカルにない場合
        if csl_style == DEFAULT_SETTINGS["csl_style"]:
            # デフォルトかつ存在しない場合、まず他のローカルファイルを提案
            selected_csl = _select_file_generic("csl", "CSL Style")
            if selected_csl:
                csl_style = str(selected_csl)
            else:
                # 他になければダウンロード試行
                downloaded = _download_csl(csl_style)
                if downloaded:
                    csl_style = str(downloaded)
                else:
                    return 1
        else:
            # 明示指定されたスタイルがない場合はダウンロード試行
            downloaded = _download_csl(csl_style)
            if downloaded:
                csl_style = str(downloaded)
            else:
                return 1

    # Output handling
    if args.output_file:
        output_path = Path(args.output_file)
        if output_path.is_dir():
            output_path = output_path / f"{input_path.stem}_cited{input_path.suffix}"
    else:
        output_path = input_path.with_name(f"{input_path.stem}_cited{input_path.suffix}")

    # Build Settings
    settings = GlobalSettings(
        pmid_regex_pattern=args.pmid_regex,
        csl_style=csl_style,
        csl_locale=args.csl_locale,
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
