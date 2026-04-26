#!/usr/bin/env python3
"""
PyRefPmid - Markdown PubMed Referencer (Refined v3.1.1)

Description:
    Markdown ファイル内の PMID を検出し、NCBI Literature Citation API を利用して
    正確な引用置換と参考文献リスト生成を高速に行います。
"""
from __future__ import annotations

__version__ = "3.1.1"
__author__ = "mfujita47 (Mitsugu Fujita)"

import argparse
import concurrent.futures
import json
import re
import sys
import threading
import time
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable

# 外部ライブラリチェック
try:
    import requests
except ImportError:
    print("Error: 'requests' library is missing. Install via 'pip install requests'.")
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
    print("Error: 'citeproc-py' library is missing. Install via 'pip install citeproc-py'.")
    sys.exit(1)

@dataclass(frozen=True)
class GlobalSettings:
    pmid_regex_pattern: str = r"(?i)\[pm(?:id)?:?\s*(\d+)\](?:\([^)]*\))?"
    csl_style: str = "elsevier-vancouver"
    csl_locale: str = "en-US"
    references_header: str = "References"
    api_base_url: str = "https://api.ncbi.nlm.nih.gov/lit/ctxp/v1/pubmed/"
    api_key: str | None = "3a88fc215344206ea89f04981d824c4ca608"
    api_timeout: float = 15.0
    max_workers: int = 5
    use_cache: bool = True

DEFAULT_SETTINGS: dict[str, Any] = {
    f.name: f.default for f in fields(GlobalSettings) if f.default is not MISSING
}

PMID = str

@dataclass
class ArticleMetadata:
    pmid: PMID
    csl_data: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and bool(self.csl_data)

    def to_dict(self) -> dict:
        return {"pmid": self.pmid, "csl_data": self.csl_data, "error": self.error}

    @classmethod
    def from_dict(cls, d: dict) -> ArticleMetadata:
        return cls(pmid=d.get("pmid", ""), csl_data=d.get("csl_data", {}), error=d.get("error"))

    def to_csl_json(self) -> dict[str, Any]:
        if self.csl_data:
            csl = self.csl_data.copy()
            csl["id"] = self.pmid
            return csl
        return {
            "id": self.pmid, "type": "article-journal",
            "title": f"[Error] {self.error or 'Failed to fetch data.'}",
            "author": [{"family": f"PMID: {self.pmid}", "given": ""}],
            "issued": {"date-parts": [[0]]}
        }

class RateLimiter:
    def __init__(self, calls_per_second: float):
        self.interval = 1.0 / calls_per_second
        self.lock = threading.Lock()
        self.last_call = 0.0

    def wait(self):
        with self.lock:
            wait_time = self.interval - (time.time() - self.last_call)
            if wait_time > 0: time.sleep(wait_time)
            self.last_call = time.time()

class PubMedClient:
    def __init__(self, settings: GlobalSettings):
        self.settings = settings
        self.limiter = RateLimiter(9.0 if settings.api_key else 2.5)
        self.session = requests.Session()

    def _fetch_single(self, pmid: PMID) -> ArticleMetadata:
        self.limiter.wait()
        params = {"format": "csl", "id": pmid}
        if self.settings.api_key: params["api_key"] = self.settings.api_key
        try:
            resp = self.session.get(self.settings.api_base_url, params=params, timeout=self.settings.api_timeout)
            if resp.status_code == 404: return ArticleMetadata(pmid=pmid, error="Not found")
            resp.raise_for_status()
            return ArticleMetadata(pmid=pmid, csl_data=resp.json())
        except Exception as e: return ArticleMetadata(pmid=pmid, error=str(e))

    def fetch_all(self, pmids: Iterable[PMID]) -> dict[PMID, ArticleMetadata]:
        unique = list(set(pmids))
        if not unique: return {}
        print(f"Fetching {len(unique)} articles...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.settings.max_workers) as executor:
            return dict(zip(unique, executor.map(self._fetch_single, unique)))

class CacheManager:
    def __init__(self, filepath: Path, use_cache: bool):
        self.filepath, self.use_cache = filepath, use_cache
        self.data: dict[PMID, ArticleMetadata] = {}
        if self.use_cache and self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.data = {k: ArticleMetadata.from_dict(v) for k, v in raw.items()}
            except Exception: print("Warning: Cache load failed.")

    def save(self):
        if not self.use_cache: return
        try:
            export = {k: v.to_dict() for k, v in self.data.items()}
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(export, f, ensure_ascii=False, indent=2)
        except Exception as e: print(f"Warning: Cache save failed ({e})")

class CitationProcessor:
    def __init__(self, settings: GlobalSettings, details_map: dict[PMID, ArticleMetadata]):
        self.settings, self.details_map = settings, details_map
        
        csl_data = [m.to_csl_json() for m in details_map.values()]
        self.style = CitationStylesStyle(str(self._find_style(settings.csl_style)), validate=False)
        self.bibliography = CitationStylesBibliography(self.style, CiteProcJSON(csl_data), formatter.plain)
        self.is_num = getattr(self.style, 'citation_format', '') == 'numeric' or \
                     any(n in settings.csl_style.lower() for n in ["ieee", "vancouver", "nature"])

    def _find_style(self, name: str) -> Path:
        for p in [Path(name), Path(f"{name}.csl")]:
            if p.exists() and p.is_file(): return p
        for p in Path.cwd().glob("*.csl"):
            if p.stem.lower() == name.lower(): return p
        print(f"Error: Style '{name}' not found."); sys.exit(1)

    def process(self, content: str, matches: list[re.Match]) -> str:
        """PMIDマッチ情報を受け取り、グルーピングと引用置換を一気に行う"""
        # 1. 連番マップ作成 (出現順)
        unique_pmids = []
        seen = set()
        for m in matches:
            p = m.group(1)
            if p not in seen: unique_pmids.append(p); seen.add(p)
        pmid_map = {p: i + 1 for i, p in enumerate(unique_pmids)}

        # 2. グルーピング (空白を挟むマッチを結合)
        groups: list[list[re.Match]] = []
        if matches:
            current_group = [matches[0]]
            for i in range(1, len(matches)):
                prev, curr = matches[i-1], matches[i]
                if content[prev.end():curr.start()].strip() == "":
                    current_group.append(curr)
                else:
                    groups.append(current_group); current_group = [curr]
            groups.append(current_group)

        # 3. 引用登録と組み立て
        registered = {}
        for grp in groups:
            pmids = sorted([m.group(1) for m in grp], key=int)
            items = [CitationItem(p) for p in pmids if p in self.details_map]
            if items:
                cit = Citation(items); self.bibliography.register(cit)
                registered[id(grp[0])] = cit

        result, last_pos = [], 0
        for grp in groups:
            start, end = grp[0].start(), grp[-1].end()
            pmids = [m.group(1) for m in grp]
            result.append(content[last_pos:start])
            
            c_str = ""
            if self.is_num:
                nums = sorted([pmid_map[p] for p in pmids if p in pmid_map])
                if nums:
                    c_str = f"[{nums[0]}-{nums[-1]}]" if len(nums) > 2 and nums[-1]-nums[0] == len(nums)-1 else f"[{','.join(map(str, nums))}]"
            
            if not c_str and id(grp[0]) in registered:
                try: c_str = str(self.bibliography.cite(registered[id(grp[0])], lambda x: None))
                except Exception: pass
            
            result.append(c_str or content[start:end])
            last_pos = end
            
        result.append(content[last_pos:])
        return "".join(result)

    def create_section(self, header_level: int, custom_header: str | None = None) -> str:
        bib_items = []
        for item in self.bibliography.bibliography():
            s = re.sub(r"\s+", " ", "".join(item)).strip()
            s = re.sub(r"^(\[\d+\]\.?|\d+\.?)(?=[^\s])", r"\1 ", s) # スペース補正
            s = re.sub(r"\.{2,}", ".", s) # 重複ピリオド
            bib_items.append(s)
        if not bib_items: return ""
        header = custom_header or f"{'#' * header_level} {self.settings.references_header}"
        return f"{header}\n\n" + "\n\n".join(bib_items) + "\n"

class ReferenceBuilder:
    def __init__(self, in_p: Path, out_p: Path, settings: GlobalSettings, cache_p: Path):
        self.in_p, self.out_p, self.settings = in_p, out_p, settings
        self.client, self.cache = PubMedClient(settings), CacheManager(cache_p, settings.use_cache)

    def build(self) -> bool:
        print(f"Processing: {self.in_p}")
        try: content = self.in_p.read_text(encoding="utf-8")
        except Exception as e: print(f"Error: {e}"); return False

        # 1. 既存セクションの同定とプレースホルダ化
        header_names = [self.settings.references_header, "Bibliography", "参考文献", "文献"]
        header_pattern = "|".join(re.escape(h) for h in header_names)
        refs_pattern = re.compile(rf"(?m)^(#+\s+(?:\d+\.\s*)?(?:{header_pattern}))\s*$", re.I)
        match = refs_pattern.search(content)
        
        placeholder = "[[PYREFPMID_REFS_PLACEHOLDER]]"
        existing_header = None
        if match:
            existing_header = match.group(1)
            next_h = re.compile(r"(?m)^#+\s+").search(content, match.end())
            main_content = content[:match.start()] + placeholder + content[next_h.start() if next_h else len(content):]
        else:
            main_content = content.rstrip() + "\n\n" + placeholder + "\n"

        # 2. PMIDスキャン (ここだけで行う)
        pmid_matches = list(re.finditer(self.settings.pmid_regex_pattern, main_content))
        if not pmid_matches:
            if self.in_p != self.out_p: self.out_p.write_text(content, encoding="utf-8", newline="\n")
            return True

        # 3. データ取得と処理
        unique_pmids = {m.group(1) for m in pmid_matches}
        cached, missing = self.cache.get_missing(unique_pmids)
        if missing:
            self.cache.data.update(self.client.fetch_all(missing)); self.cache.save()
        
        processor = CitationProcessor(self.settings, {p: self.cache.data[p] for p in unique_pmids if p in self.cache.data})
        new_content = processor.process(main_content, pmid_matches)
        
        # 4. 文献リスト生成と挿入
        h_match = re.search(r"^(#+)\s+", content, re.M)
        ref_sec = processor.create_section(len(h_match.group(1)) if h_match else 2, existing_header)
        
        self.out_p.parent.mkdir(parents=True, exist_ok=True)
        self.out_p.write_text(new_content.replace(placeholder, ref_sec), encoding="utf-8", newline="\n")
        print(f"✓ Saved: {self.out_p}"); return True

def _select_file_generic(ext: str, label: str) -> Path | None:
    cands = list(Path.cwd().glob(f"*.{ext}"))
    if len(cands) == 1: print(f"Auto-selected: {cands[0].name}"); return cands[0]
    if sys.stdin and sys.stdin.isatty() and cands:
        print(f"Select {label}:")
        for i, f in enumerate(cands, 1): print(f"  {i}. {f.name}")
        print("  0. File Dialog")
        c = input("Select: ")
        if c.isdigit() and 1 <= int(c) <= len(cands): return cands[int(c)-1]
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        path = filedialog.askopenfilename(title=f"Select {label}", filetypes=[(label, f"*.{ext}"), ("All", "*.*")])
        root.destroy(); return Path(path) if path else None
    except Exception: return None

def _resolve_csl_style(style: str) -> str:
    """スタイル名からローカルファイル、またはGitHubからのダウンロードを解決する"""
    if Path(style).exists() or Path(f"{style}.csl").exists(): return style
    local = next((p for p in Path.cwd().glob("*.csl") if p.stem.lower() == style.lower()), None)
    if local: return str(local)
    
    for url in [f"https://raw.githubusercontent.com/citation-style-language/styles/master/{style.lower()}.csl",
                f"https://raw.githubusercontent.com/citation-style-language/styles/master/dependent/{style.lower()}.csl"]:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                p = Path(f"{style.lower()}.csl")
                p.write_text(r.text, encoding="utf-8", newline="\n")
                print(f"✓ Downloaded style: {style}"); return str(p)
        except Exception: continue
    return style

def main() -> int:
    parser = argparse.ArgumentParser(description="PyRefPmid v3.1.1")
    parser.add_argument("input_file", nargs="?")
    parser.add_argument("-o", "--output-file")
    parser.add_argument("--csl-style", default=DEFAULT_SETTINGS["csl_style"])
    args = parser.parse_args()

    in_p = Path(args.input_file) if args.input_file else _select_file_generic("md", "Markdown")
    if not in_p or not in_p.exists(): return 1

    settings = GlobalSettings(csl_style=_resolve_csl_style(args.csl_style))
    out_p = Path(args.output_file) if args.output_file else in_p.with_name(f"{in_p.stem}_cited{in_p.suffix}")
    return 0 if ReferenceBuilder(in_p, out_p, settings, in_p.with_suffix(".json")).build() else 1

if __name__ == "__main__": sys.exit(main())
