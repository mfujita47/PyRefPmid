# -*- coding: utf-8 -*-
import re
import argparse
import requests
import time
from collections import OrderedDict
import os
import tkinter as tk
from tkinter import filedialog
import logging
import textwrap # 追加

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PubMedProcessor:
  """
  Markdown ファイル内の PubMed 引用を処理し、
  References リストを生成・置換するクラス。
  """
  DEFAULT_PMID_REGEX_PATTERN = r'\[pm(?:id)?\s+(\d+)\]\([^)]*\)' # PMID 抽出パターン
  DEFAULT_AUTHOR_THRESHOLD = 0 # 著者名表示の閾値 (0 は全員)
  DEFAULT_CITATION_FORMAT = '({number})'
  DEFAULT_REFERENCE_ITEM_FORMAT = '{number}. {authors}. {title}. {journal} {year};{volume}:{pages}. doi: {doi}. PMID: {pmid}.'
  DEFAULT_PUBMED_API_BASE_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
  DEFAULT_API_REQUEST_DELAY = 0.4 # 3リクエスト/秒 以下

  def __init__(self, pmid_regex_pattern=None, author_threshold=None, citation_format=None, ref_item_format=None, api_base_url=None, api_delay=None):
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

  def extract_pmids(self, markdown_content):
    """Markdown コンテンツから指定されたパターンの PMID を抽出する"""
    try:
      raw_pmids = re.findall(self.pmid_regex_pattern, markdown_content, flags=re.IGNORECASE)
      # 重複を許さず、出現順を保持
      ordered_pmids = list(OrderedDict.fromkeys(raw_pmids))
      logging.info(f"抽出された PMID (重複除去・順序保持): {ordered_pmids}")
    except re.error as e:
      logging.error(f"PMID 抽出のための正規表現パターンが無効です: {self.pmid_regex_pattern} - {e}")
      return []
    return ordered_pmids

  def fetch_pubmed_details(self, pmids):
    """PubMed API を使用して PMID リストに対応する論文詳細を取得する"""
    if not pmids:
      logging.warning("取得対象の PMID がありません。")
      return {}, []

    details = {}
    not_found_pmids = []
    pmid_string = ','.join(pmids)
    url = f"{self.api_base_url}esummary.fcgi?db=pubmed&id={pmid_string}&retmode=json"

    logging.info(f"PubMed API にリクエスト中: {url}")
    try:
      response = requests.get(url)
      response.raise_for_status()
      data = response.json()
      logging.info("PubMed API からレスポンスを受信")

      results = data.get('result')
      if not results or 'uids' not in results:
        logging.warning("PubMed API から有効な結果が得られませんでした。")
        not_found_pmids.extend(pmids)
        return {}, list(set(not_found_pmids)) # 重複を除去して返す

      returned_uids = results.get('uids', [])
      requested_pmids_set = set(pmids)
      returned_uids_set = set(returned_uids)
      missing_in_response = list(requested_pmids_set - returned_uids_set)

      if missing_in_response:
        logging.warning(f"API レスポンスに以下の PMID が含まれていません: {missing_in_response}")
        not_found_pmids.extend(missing_in_response)
        for missing_pmid in missing_in_response:
          details[missing_pmid] = {'error': 'Not found in API response'}

      for pmid in returned_uids:
        if pmid not in results:
          logging.warning(f"PMID {pmid} の詳細情報が results 内に見つかりません。")
          if pmid not in not_found_pmids:
            not_found_pmids.append(pmid)
          details[pmid] = {'error': 'Details not found in results dict'}
          continue

        entry = results[pmid]
        if 'error' in entry:
          logging.warning(f"PMID {pmid} の詳細取得で API エラー: {entry['error']}")
          if pmid not in not_found_pmids:
            not_found_pmids.append(pmid)
          details[pmid] = entry
          continue

        authors_list = entry.get('authors', [])
        # 著者名の整形 (閾値に基づいて)
        if self.author_threshold > 0 and len(authors_list) > self.author_threshold:
          authors = ', '.join([a['name'] for a in authors_list[:self.author_threshold]]) + ', et al.'
        else:
          authors = ', '.join([author['name'] for author in authors_list])

        doi = ''
        articleids = entry.get('articleids', [])
        for aid in articleids:
          if aid.get('idtype') == 'doi':
            doi = aid.get('value', '')
            break
        # elocationid もフォールバックとしてチェック (形式が doi: XXXXX の場合)
        if not doi and entry.get('elocationid', '').startswith('doi:'):
          doi = entry.get('elocationid', '').replace('doi: ', '')


        details[pmid] = {
          'authors': authors,
          'year': entry.get('pubdate', '').split(' ')[0],
          'title': entry.get('title', 'N/A'),
          'journal': entry.get('source', 'N/A'),
          'volume': entry.get('volume', ''),
          'issue': entry.get('issue', ''),
          'pages': entry.get('pages', ''),
          'pmid': pmid,
          'doi': doi
        }
        # API リクエストの間隔を空ける
        time.sleep(self.api_delay)

    except requests.exceptions.RequestException as e:
      logging.error(f"PubMed API への接続に失敗しました - {e}")
      return {}, list(set(not_found_pmids)) # 接続失敗時も見つからなかったリストは返す
    except Exception as e:
      logging.error(f"PubMed データの処理中に予期せぬエラーが発生しました - {e}")
      return {}, list(set(not_found_pmids))

    valid_details_count = sum(1 for d in details.values() if 'error' not in d)
    logging.info(f"取得した有効な論文詳細数: {valid_details_count}")
    unique_not_found = list(set(not_found_pmids))
    if unique_not_found:
      logging.warning(f"見つからなかった、または詳細取得に失敗した PMID ({len(unique_not_found)}件): {unique_not_found}")

    self.pubmed_details = details
    self.not_found_pmids = unique_not_found
    return details, unique_not_found

  def _format_reference_item(self, details, number):
    """指定されたフォーマット文字列に従って References の項目を整形する"""
    try:
      return self.ref_item_format.format(
        number=number,
        authors=details.get('authors', 'N/A'),
        year=details.get('year', 'N/A'),
        title=details.get('title', 'N/A').rstrip('. '),
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
        # 論文情報が取得できなかった場合の代替表示
        error_msg = details.get('error', '不明なエラー') if details else '取得失敗'
        items.append(f"{number}. [PMID {pmid}] - 論文情報の取得に失敗しました ({error_msg})。")

    if not items:
      logging.info("有効な参照項目がないため、References セクションは生成されません。")
      return ""

    # ヘッダーとリストの間に空行を挿入
    return f"\n\n{header}\n\n" + "\n".join(items)

  def detect_header_level(self, markdown_content):
    """Markdownコンテンツから主要セクションのヘッダーレベルを検出する"""
    # 一般的なセクション名を正規表現で検索 (大文字小文字を区別しない)
    matches = re.findall(r'^(#+)\s+(Introduction|Methods|Results|Discussion|Conclusion|Background|Case Report|Abstract|はじめに|方法|結果|考察|結論|背景|症例報告|要旨)', markdown_content, re.MULTILINE | re.IGNORECASE)
    if matches:
      level = len(matches[0][0])
      logging.info(f"主要セクションのヘッダーレベル {level} を検出しました。")
      return level
    else:
      logging.warning("主要セクションが見つかりませんでした。デフォルトのヘッダーレベル 2 を使用します。")
      return 2

  def replace_citations(self, markdown_content):
    """Markdown コンテンツ内の PMID 参照を指定された形式に置換する"""
    """Markdown コンテンツ内の PMID 参照を指定された形式に置換する"""
    output_content = markdown_content
    matches = []
    try:
        # finditer を使って全てのマッチオブジェクトとその位置を取得
        for match in re.finditer(self.pmid_regex_pattern, markdown_content, re.IGNORECASE):
            # 最初のキャプチャグループが PMID であると仮定
            if match.groups():
                pmid = match.group(1)
                if pmid in self.pmid_to_number_map:
                    # マッチの開始位置、終了位置、PMID を保存
                    matches.append((match.start(), match.end(), pmid))
            else:
                # キャプチャグループがない場合（パターンが (\d+) を含まないなど）
                logging.warning(f"パターン '{self.pmid_regex_pattern}' は PMID をキャプチャしませんでした。マッチ: {match.group(0)}")

    except re.error as e:
        logging.error(f"引用置換のための正規表現パターン処理中にエラーが発生しました: {e}")
        return markdown_content # エラー時は元のコンテンツを返す
    except Exception as e:
        logging.error(f"引用検索中に予期せぬエラーが発生しました: {e}")
        return markdown_content

    if not matches:
        logging.info("置換対象の引用が見つかりませんでした。")
        return output_content

    # 新しい文字列を構築するためのリスト
    new_content_parts = []
    last_end = 0
    # マッチ箇所を開始位置でソート（通常 finditer は出現順に返す）
    sorted_matches = sorted(matches, key=lambda x: x[0])

    for start, end, pmid in sorted_matches:
        try:
            # マップに PMID が存在するか再確認 (fetch で失敗した PMID は除くため)
            if pmid in self.pmid_to_number_map:
                number = self.pmid_to_number_map[pmid]
                citation_replace_str = self.citation_format.format(number=number)
                # 前回の終了位置から今回の開始位置までの部分を追加
                new_content_parts.append(output_content[last_end:start])
                # 置換後の文字列を追加
                new_content_parts.append(citation_replace_str)
                last_end = end
            else:
                # マップにない場合（fetch失敗など）は元のテキストを残す
                new_content_parts.append(output_content[last_end:end])
                last_end = end
        except KeyError as e:
            # citation_format のキーエラーなど
            logging.error(f"引用符のフォーマット中にエラーが発生しました。キー: {e}, フォーマット: {self.citation_format}")
            # エラー時は元の部分を追加
            new_content_parts.append(output_content[last_end:start]) # エラー発生前の部分
            new_content_parts.append(output_content[start:end]) # エラー発生箇所（元のまま）
            last_end = end
        except Exception as e:
            logging.error(f"引用符の置換中に予期せぬエラーが発生しました: {e}")
            # エラー時は元の部分を追加
            new_content_parts.append(output_content[last_end:start])
            new_content_parts.append(output_content[start:end])
            last_end = end

    # 最後のマッチ以降の部分を追加
    new_content_parts.append(output_content[last_end:])

    final_output = "".join(new_content_parts)

    logging.info("本文中の引用を置換しました。")
    return final_output

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

    # 1. PMID を抽出
    pmids = self.extract_pmids(content)
    if not pmids:
      logging.warning("PMID 形式の引用が見つかりませんでした。処理を終了します。")
      return False # PMIDがない場合は処理しない

    # 2. PubMed から詳細を取得
    self.fetch_pubmed_details(pmids)

    # 有効な詳細が一つもない場合は警告（エラー情報は除く）
    has_valid_details = any('error' not in detail for detail in self.pubmed_details.values())
    if not has_valid_details and self.pubmed_details: # 詳細辞書が空でない場合のみ警告
      logging.warning("PubMed から有効な論文情報を取得できませんでした。")

    # 3. PMID と連番のマッピングを作成 (出現順)
    self.pmid_to_number_map = {pmid: i + 1 for i, pmid in enumerate(pmids)}
    logging.info(f"PMID と番号のマッピング: {self.pmid_to_number_map}")

    # 4. 本文中の引用を置換
    modified_content = self.replace_citations(content)

    # 5. ヘッダーレベルを検出し、References ヘッダーを作成
    header_level = self.detect_header_level(content)
    dynamic_references_header = '#' * header_level + ' References'

    # 6. References セクションを作成
    references_section = self.create_references_section(dynamic_references_header)

    # 7. 既存の References セクションを削除
    # 大文字小文字を区別せず、セクション全体を削除
    # ヘッダーの # の数に依存しないように修正
    modified_content_no_refs = re.sub(r'\n\n#+\s+References\s*\n.*', '', modified_content, flags=re.DOTALL | re.IGNORECASE)

    # 8. 最終的な Markdown コンテンツを結合
    final_content = modified_content_no_refs.rstrip() + references_section

    # 9. 結果をファイルに書き込み
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
  root.withdraw() # メインウィンドウを表示しない
  filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
  root.destroy() # ダイアログが閉じられた後に Tkinter ルートウィンドウを破棄
  if not filepath:
    logging.warning("ファイルが選択されませんでした。")
    return None
  return filepath

# --- メイン処理 ---
def main():
  parser = argparse.ArgumentParser(description='Markdown ファイル内の PubMed 引用を処理し、References リストを生成・置換します。')
  parser.add_argument('input_file', nargs='?', default=None, help='処理対象の Markdown ファイルパス (省略時はダイアログ表示)')
  parser.add_argument('-o', '--output_file', help='出力先のファイルパス (指定しない場合は input_file に _cited を付与)')

  # PubMedProcessor 設定の引数を追加
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
      # このケースは通常発生しないはず
      logging.error("入力ファイルパスが不明なため、出力ファイル名を決定できません。")
      return

  # PubMedProcessor インスタンスを作成 (新しい引数を追加)
  processor = PubMedProcessor(
    pmid_regex_pattern=args.pmid_pattern,
    author_threshold=args.author_threshold,
    citation_format=args.citation_format,
    ref_item_format=args.ref_item_format,
    api_base_url=args.api_base_url,
    api_delay=args.api_delay
  )

  # ファイル処理を実行
  success = processor.process_file(input_filepath, output_filepath)

  if success:
    logging.info("処理が正常に完了しました。")
  else:
    logging.error("処理中にエラーが発生しました。")

if __name__ == "__main__":
  main()
