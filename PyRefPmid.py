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
from tkinter import filedialog

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PubMedProcessor:
  """Markdown ファイル内の PubMed 引用を処理し、References リストを生成・置換するクラス"""
  DEFAULT_PMID_REGEX_PATTERN = r'\[pm(?:id)?\s+(\d+)\]\([^)]*\)'
  DEFAULT_AUTHOR_THRESHOLD = 0
  DEFAULT_CITATION_FORMAT = '({number})'
  DEFAULT_REFERENCE_ITEM_FORMAT = '{number}. {authors}. {title} {journal} {year};{volume}:{pages}. doi: {doi}. [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)'
  DEFAULT_PUBMED_API_BASE_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
  DEFAULT_API_REQUEST_DELAY = 0.4

  def __init__(self, pmid_regex_pattern=None, author_threshold=None, citation_format=None, ref_item_format=None, api_base_url=None, api_delay=None, cache_file=None, use_cache=True):
    """
    PubMedProcessor を初期化します。
    Args:
      citation_format (str, optional): 本文中の引用形式。デフォルトは DEFAULT_CITATION_FORMAT。
      pmid_regex_pattern (str, optional): PMID を抽出する正規表現パターン。デフォルトは DEFAULT_PMID_REGEX_PATTERN。
      author_threshold (int, optional): 著者名表示の閾値 (0 は全員)。デフォルトは DEFAULT_AUTHOR_THRESHOLD。
      citation_format (str, optional): 本文中の引用形式。デフォルトは DEFAULT_CITATION_FORMAT。
      ref_item_format (str, optional): References の各項目形式。デフォルトは DEFAULT_REFERENCE_ITEM_FORMAT。
      api_base_url (str, optional): PubMed API のベース URL。デフォルトは DEFAULT_PUBMED_API_BASE_URL。
      api_delay (float, optional): PubMed API へのリクエスト間隔 (秒)。デフォルトは DEFAULT_API_REQUEST_DELAY。
      cache_file (str, optional): キャッシュファイルのパス。指定しない場合は OS の一時フォルダに '.pubmed_cache.json' が作成されます。
      use_cache (bool, optional): キャッシュを使用するかどうか。デフォルトは True。
    """
    self.pmid_regex_pattern = pmid_regex_pattern or self.DEFAULT_PMID_REGEX_PATTERN
    self.author_threshold = author_threshold if author_threshold is not None else self.DEFAULT_AUTHOR_THRESHOLD
    self.citation_format = citation_format or self.DEFAULT_CITATION_FORMAT
    self.ref_item_format = ref_item_format or self.DEFAULT_REFERENCE_ITEM_FORMAT
    self.api_base_url = api_base_url or self.DEFAULT_PUBMED_API_BASE_URL
    self.api_delay = api_delay if api_delay is not None else self.DEFAULT_API_REQUEST_DELAY
    self.pubmed_details = {}
    self.not_found_pmids = []
    self.pmid_to_number_map = {}
    self.use_cache = use_cache
    if cache_file:
      self.cache_file = cache_file
    else:
      self.cache_file = os.path.join(tempfile.gettempdir(), '.pubmed_cache.json')
    self.cache_data = {}
    if self.use_cache:
      self._load_cache()
      logging.info(f"キャッシュファイルパス: {self.cache_file}")

  def extract_pmids(self, markdown_content):
    """Markdown コンテンツから指定されたパターンの PMID を抽出する"""
    try:
      raw_pmids = re.findall(self.pmid_regex_pattern, markdown_content, flags=re.IGNORECASE)
      ordered_pmids = list(OrderedDict.fromkeys(raw_pmids))
      logging.info(f"抽出された PMID (重複除去・順序保持): {ordered_pmids}")
    except re.error as e:
      logging.error(f"PMID 抽出のための正規表現パターンが無効です: {self.pmid_regex_pattern} - {e}")
      return []
    return ordered_pmids

  def _load_cache(self):
    """キャッシュファイルからデータを読み込む"""
    try:
      if os.path.exists(self.cache_file):
        with open(self.cache_file, 'r', encoding='utf-8') as f:
          self.cache_data = json.load(f)
        logging.info(f"キャッシュファイルを読み込みました: {self.cache_file}")
      else:
        logging.info("キャッシュファイルが見つかりません。新規に作成されます。")
        self.cache_data = {}
    except json.JSONDecodeError:
      logging.warning(f"キャッシュファイル '{self.cache_file}' の形式が不正です。キャッシュは無視されます。")
      self.cache_data = {}
    except Exception as e:
      logging.error(f"キャッシュファイルの読み込み中にエラーが発生しました: {e}")
      self.cache_data = {}

  def _save_cache(self):
    """現在のキャッシュデータをファイルに保存する"""
    if not self.use_cache:
      return
    try:
      with open(self.cache_file, 'w', encoding='utf-8') as f:
        json.dump(self.cache_data, f, ensure_ascii=False, indent=2)
      logging.info(f"キャッシュをファイルに保存しました: {self.cache_file}")
    except Exception as e:
      logging.error(f"キャッシュファイルの保存中にエラーが発生しました: {e}")

  def _get_details_from_cache(self, pmids):
    """指定された PMID リストからキャッシュに存在する詳細を取得する"""
    details_from_cache = {}
    pmids_not_in_cache = []
    not_found_in_cache = []
    if not self.use_cache:
      return {}, list(pmids), []
    for pmid in pmids:
      if pmid in self.cache_data:
        logging.info(f"PMID {pmid} はキャッシュから取得しました。")
        details_from_cache[pmid] = self.cache_data[pmid]
        if 'error' in self.cache_data[pmid]:
          not_found_in_cache.append(pmid)
      else:
        pmids_not_in_cache.append(pmid)
    return details_from_cache, pmids_not_in_cache, not_found_in_cache

  def _fetch_details_from_api(self, pmids_to_fetch):
    """指定されたPMIDリストの詳細をPubMed APIから取得する"""
    if not pmids_to_fetch:
      return {}, []
    logging.info(f"API で取得する PMID ({len(pmids_to_fetch)}件): {pmids_to_fetch}")
    pmid_string = ','.join(pmids_to_fetch)
    url = f"{self.api_base_url}esummary.fcgi?db=pubmed&id={pmid_string}&retmode=json"
    api_details = {}
    api_not_found = []
    logging.info(f"PubMed API にリクエスト中: {url}")
    try:
      response = requests.get(url)
      response.raise_for_status()
      data = response.json()
      logging.info("PubMed API からレスポンスを受信")
      results = data.get('result')
      if not results or 'uids' not in results:
        logging.warning("PubMed API から有効な結果が得られませんでした。")
        api_not_found.extend(pmids_to_fetch)
        for pmid in pmids_to_fetch:
          api_details[pmid] = {'error': 'Not found in API response'}
        return api_details, api_not_found
      returned_uids = results.get('uids', [])
      requested_pmids_set = set(pmids_to_fetch)
      returned_uids_set = set(returned_uids)
      missing_in_response = list(requested_pmids_set - returned_uids_set)
      if missing_in_response:
        logging.warning(f"API レスポンスに以下の PMID が含まれていません: {missing_in_response}")
        api_not_found.extend(missing_in_response)
        for missing_pmid in missing_in_response:
          api_details[missing_pmid] = {'error': 'Not found in API response'}
      for pmid in returned_uids:
        if pmid not in results:
          logging.warning(f"PMID {pmid} の詳細情報が results 内に見つかりません。")
          if pmid not in api_not_found: api_not_found.append(pmid)
          api_details[pmid] = {'error': 'Details not found in results dict'}
          continue
        entry = results[pmid]
        if 'error' in entry:
          logging.warning(f"PMID {pmid} の詳細取得で API エラー: {entry['error']}")
          if pmid not in api_not_found: api_not_found.append(pmid)
          api_details[pmid] = entry
          continue
        authors_list = entry.get('authors', [])
        author_names = [a.get('name', 'N/A') for a in authors_list]
        if self.author_threshold > 0 and len(author_names) > self.author_threshold:
          authors = ', '.join(author_names[:self.author_threshold]) + ', et al'
        else:
          authors = ', '.join(author_names)
        articleids = entry.get('articleids', [])
        doi = next((aid.get('value', '') for aid in articleids if aid.get('idtype') == 'doi'), '')
        if not doi and entry.get('elocationid', '').startswith('doi:'):
          doi = entry.get('elocationid', '').replace('doi: ', '')
        api_details[pmid] = {
          'authors': authors, 'year': entry.get('pubdate', '').split(' ')[0],
          'title': entry.get('title', 'N/A'), 'journal': entry.get('source', 'N/A'),
          'volume': entry.get('volume', ''), 'issue': entry.get('issue', ''),
          'pages': entry.get('pages', ''), 'pmid': pmid, 'doi': doi
        }
        time.sleep(self.api_delay)
    except requests.exceptions.RequestException as e:
      logging.error(f"PubMed API への接続に失敗しました - {e}")
      api_not_found.extend(pmids_to_fetch)
      for pmid in pmids_to_fetch:
        api_details[pmid] = {'error': f'API connection failed: {e}'}
    except Exception as e:
      logging.error(f"PubMed API データ処理中に予期せぬエラーが発生しました - {e}")
      api_not_found.extend(pmids_to_fetch)
      for pmid in pmids_to_fetch:
        api_details[pmid] = {'error': f'Unexpected error during API fetch: {e}'}
    return api_details, list(set(api_not_found))

  def fetch_pubmed_details(self, pmids):
    """PubMed API またはキャッシュを使用して PMID リストに対応する論文詳細を取得する"""
    if not pmids:
      logging.warning("取得対象の PMID がありません。")
      return {}, []
    details_from_cache, pmids_to_fetch, not_found_in_cache = self._get_details_from_cache(pmids)
    api_details, api_not_found = self._fetch_details_from_api(pmids_to_fetch)
    final_details = {**details_from_cache, **api_details}
    final_not_found = list(set(not_found_in_cache + api_not_found)) # 重複除去
    if self.use_cache and api_details:
      for pmid, detail_data in api_details.items():
        self.cache_data[pmid] = detail_data
      self._save_cache()
    self.pubmed_details = final_details
    self.not_found_pmids = final_not_found
    valid_details_count = sum(1 for d in final_details.values() if 'error' not in d)
    logging.info(f"取得またはキャッシュから読み込んだ有効な論文詳細数: {valid_details_count}")
    if final_not_found:
      logging.warning(f"見つからなかった、または詳細取得に失敗した PMID ({len(final_not_found)}件): {final_not_found}")
    return final_details, final_not_found

  def _format_reference_item(self, details, number):
    """指定されたフォーマット文字列に従って References の項目を整形する"""
    try:
      return self.ref_item_format.format(
        number=number,
        authors=details.get('authors', 'N/A'),
        year=details.get('year', 'N/A'),
        title=details.get('title', 'N/A'),
        journal=details.get('journal', 'N/A'),
        volume=details.get('volume', ''),
        issue=details.get('issue', ''),
        pages=details.get('pages', ''),
        pmid=details.get('pmid', 'N/A'),
        doi=details.get('doi', '')
      ).strip()
    except KeyError as e:
      logging.error(f"参照項目のフォーマット中にエラーが発生しました。キー: {e}, フォーマット: {self.ref_item_format}, 詳細: {details}")
      return f"{number}. [PMID {details.get('pmid', 'N/A')}] - フォーマットエラー"
    except Exception as e:
      logging.error(f"参照項目のフォーマット中に予期せぬエラーが発生しました: {e}")
      return f"{number}. [PMID {details.get('pmid', 'N/A')}] - 不明なフォーマットエラー"

  def create_references_section(self, header):
    """References セクションの Markdown 文字列を生成する"""
    if not self.pubmed_details:
      logging.info("論文詳細データがないため、References セクションは生成されません。")
      return ""
    items = []
    for pmid, number in self.pmid_to_number_map.items():
      details = self.pubmed_details.get(pmid)
      if details and 'error' not in details:
        item_str = self._format_reference_item(details, number)
        items.append(item_str)
      else:
        error_msg = details.get('error', '不明なエラー') if details else '取得失敗'
        items.append(f"{number}. [PMID {pmid}] - 論文情報の取得に失敗しました ({error_msg})。")
    if not items:
      logging.info("有効な参照項目がないため、References セクションは生成されません。")
      return ""
    return f"\n\n{header}\n\n" + "\n".join(items)

  def detect_header_level(self, markdown_content):
    """Markdownコンテンツから主要セクションのヘッダーレベルを検出する"""
    matches = re.findall(r'^(#+)\s+(Introduction|Methods|Results|Discussion|Conclusion|Background|Case Report|Abstract|はじめに|方法|結果|考察|結論|背景|症例報告|要旨)', markdown_content, re.MULTILINE | re.IGNORECASE)
    if matches:
      level = len(matches[0][0])
      logging.info(f"主要セクションのヘッダーレベル {level} を検出しました。")
      return level
    else:
      logging.warning("主要セクションが見つかりませんでした。デフォルトのヘッダーレベル 2 を使用します。")
      return 2

  def _citation_replacer(self, match):
    """re.sub のコールバック関数: マッチした PMID 参照を置換する"""
    try:
      pmid = match.group(1)
      if pmid in self.pmid_to_number_map:
        number = self.pmid_to_number_map[pmid]
        return self.citation_format.format(number=number)
      else:
        logging.warning(f"PMID {pmid} は番号マップに見つかりません。引用符は置換されません: {match.group(0)}")
        return match.group(0)
    except IndexError:
      logging.error(f"PMID パターン '{self.pmid_regex_pattern}' が PMID をキャプチャしませんでした。マッチ: {match.group(0)}")
      return match.group(0)
    except KeyError as e:
      logging.error(f"引用符のフォーマット中にエラーが発生しました。キー: {e}, フォーマット: {self.citation_format}")
      return match.group(0)
    except Exception as e:
      logging.error(f"引用符の置換中に予期せぬエラーが発生しました ({pmid=}): {e}")
      return match.group(0)

  def replace_citations(self, markdown_content):
    """Markdown コンテンツ内の PMID 参照を指定された形式に置換する"""
    try:
      modified_content = re.sub(
        self.pmid_regex_pattern,
        self._citation_replacer,
        markdown_content,
        flags=re.IGNORECASE
      )
      logging.info("本文中の引用を置換しました。")
      return modified_content
    except re.error as e:
      logging.error(f"引用置換のための正規表現パターン処理中にエラーが発生しました: {e}")
      return markdown_content
    except Exception as e:
      logging.error(f"引用置換プロセス全体で予期せぬエラーが発生しました: {e}")
      return markdown_content

  def process_file(self, input_filepath, output_filepath):
    """Markdown ファイルを処理して引用を置換し、References を追加する"""
    logging.info(f"処理開始: {input_filepath}")
    try:
      with open(input_filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    except FileNotFoundError:
      logging.error(f"入力ファイルが見つかりません - {input_filepath}")
      return False
    except Exception as e:
      logging.error(f"ファイル読み込み中にエラーが発生しました - {e}")
      return False
    pmids = self.extract_pmids(content)
    if not pmids:
      logging.warning("PMID 形式の引用が見つかりませんでした。処理を終了します。")
      return False
    self.fetch_pubmed_details(pmids)
    has_valid_details = any('error' not in detail for detail in self.pubmed_details.values())
    if not has_valid_details and self.pubmed_details:
      logging.warning("PubMed から有効な論文情報を取得できませんでした。")
    self.pmid_to_number_map = {pmid: i + 1 for i, pmid in enumerate(pmids)}
    logging.info(f"PMID と番号のマッピング: {self.pmid_to_number_map}")
    modified_content = self.replace_citations(content)
    header_level = self.detect_header_level(content)
    dynamic_references_header = '#' * header_level + ' References'
    references_section = self.create_references_section(dynamic_references_header)
    modified_content_no_refs = re.sub(r'\n\n#+\s+References\s*\n.*', '', modified_content, flags=re.DOTALL | re.IGNORECASE)
    final_content = modified_content_no_refs.rstrip() + references_section
    try:
      with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(final_content)
      logging.info(f"処理完了。結果をファイルに出力しました: {output_filepath}")
      if self.not_found_pmids:
        logging.warning(f"取得できなかった PMID があります: {self.not_found_pmids}")
      return True
    except Exception as e:
      logging.error(f"ファイル書き込み中にエラーが発生しました - {e}")
      return False

# --- ファイル選択ダイアログ関数 ---
def ask_for_file(title="ファイルを選択してください", filetypes=[("Markdown files", "*.md"), ("All files", "*.*")]):
  """ファイル選択ダイアログを表示してファイルパスを取得する"""
  root = tk.Tk()
  root.withdraw()
  filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
  root.destroy()
  if not filepath:
    logging.warning("ファイルが選択されませんでした。")
    return None
  return filepath

# --- メイン処理 ---
def main():
  parser = argparse.ArgumentParser(description='Markdown ファイル内の PubMed 引用を処理し、References リストを生成・置換します。')
  parser.add_argument('input_file', nargs='?', default=None, help='処理対象の Markdown ファイルパス (省略時はダイアログ表示)')
  parser.add_argument('-o', '--output_file', help='出力先のファイルパス (指定しない場合は input_file に _cited を付与)')
  parser.add_argument('--pmid-pattern', default=PubMedProcessor.DEFAULT_PMID_REGEX_PATTERN,
    help=textwrap.dedent(fr'''\
    Markdown 内の PMID を抽出するための正規表現パターン。
    PMID 自体をキャプチャグループ `(\d+)` で囲む必要があります。
    (デフォルト: "{PubMedProcessor.DEFAULT_PMID_REGEX_PATTERN}")'''))
  parser.add_argument('--author-threshold', type=int, default=PubMedProcessor.DEFAULT_AUTHOR_THRESHOLD,
    help=f'References に表示する著者名の最大数。0 を指定すると全員表示します。(デフォルト: {PubMedProcessor.DEFAULT_AUTHOR_THRESHOLD})')
  parser.add_argument('--citation-format', default=PubMedProcessor.DEFAULT_CITATION_FORMAT,
    help=f'本文中の引用形式。`{{number}}` で参照番号を挿入します。(デフォルト: "{PubMedProcessor.DEFAULT_CITATION_FORMAT}")')
  parser.add_argument('--ref-item-format', default=PubMedProcessor.DEFAULT_REFERENCE_ITEM_FORMAT,
    help=textwrap.dedent(f'''\
    References の各項目形式。以下のプレースホルダーを使用できます:
    {{number}}, {{authors}}, {{title}}, {{journal}}, {{year}}, {{volume}}, {{issue}}, {{pages}}, {{doi}}, {{pmid}}
    (デフォルト: "{PubMedProcessor.DEFAULT_REFERENCE_ITEM_FORMAT}")'''))
  parser.add_argument('--api-delay', type=float, default=PubMedProcessor.DEFAULT_API_REQUEST_DELAY,
    help=f'PubMed API へのリクエスト間隔 (秒) (デフォルト: {PubMedProcessor.DEFAULT_API_REQUEST_DELAY})')
  parser.add_argument('--api-base-url', default=PubMedProcessor.DEFAULT_PUBMED_API_BASE_URL,
    help=f'PubMed API のベース URL (デフォルト: {PubMedProcessor.DEFAULT_PUBMED_API_BASE_URL})')
  parser.add_argument('--cache-file', default=None,
    help='キャッシュファイルのパス (デフォルト: OS の一時フォルダ内の .pubmed_cache.json)')
  parser.add_argument('--use-cache', action=argparse.BooleanOptionalAction, default=True,
    help='キャッシュ機能を使用するかどうか (デフォルト: 使用する / --no-cache で無効化)')
  args = parser.parse_args()
  input_filepath = args.input_file
  if input_filepath is None:
    logging.info("入力ファイルが指定されていません。ファイル選択ダイアログを開きます。")
    input_filepath = ask_for_file(title="処理する Markdown ファイルを選択してください")
    if input_filepath is None:
      logging.error("入力ファイルが選択されなかったため、処理をキャンセルしました。")
      return
  output_filepath = args.output_file
  if not output_filepath:
    if input_filepath:
      base, ext = os.path.splitext(input_filepath)
      output_filepath = f"{base}_cited{ext}"
    else:
      logging.error("入力ファイルパスが不明なため、出力ファイル名を決定できません。")
      return
  processor = PubMedProcessor(
    pmid_regex_pattern=args.pmid_pattern,
    author_threshold=args.author_threshold,
    citation_format=args.citation_format,
    ref_item_format=args.ref_item_format,
    api_base_url=args.api_base_url,
    api_delay=args.api_delay,
    cache_file=args.cache_file,
    use_cache=args.use_cache
  )
  success = processor.process_file(input_filepath, output_filepath)
  if success:
    logging.info("処理が正常に完了しました。")
  else:
    logging.error("処理中にエラーが発生しました。")

if __name__ == "__main__":
  main()
