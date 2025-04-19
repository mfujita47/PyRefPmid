# -*- coding: utf-8 -*-
import re
import argparse
import requests
import time
from collections import OrderedDict
import os # os モジュールをインポート
import tkinter as tk
from tkinter import filedialog

# --- 設定可能なパラメータ ---

# 本文中の引用形式 (例: '({number})', '[{number}]', '{authors} ({year})')
CITATION_FORMAT = '({number})'

# References リストの各項目の形式
# 利用可能なプレースホルダー: {number}, {authors}, {year}, {title}, {journal}, {volume}, {issue}, {pages}, {pmid}, {doi}
REFERENCE_ITEM_FORMAT = '{number}. {authors}. {title}. {journal} {year};{volume}:{pages}. doi: {doi}. PMID: {pmid}.'

# PubMed API (E-utilities) のベース URL
PUBMED_API_BASE_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'

# PubMed API へのリクエスト間隔 (秒) - NCBI の利用規約に従う
API_REQUEST_DELAY = 0.4 # 3リクエスト/秒 以下

# --- 関数定義 ---

def extract_pmids(markdown_content):
    """Markdown コンテンツから [PMID xxxxx] 形式の PMID を抽出する"""
    raw_pmids = re.findall(r'\[PMID\s+(\d+)\]', markdown_content) # 正規表現で PMID を抽出
    pmids = OrderedDict.fromkeys(raw_pmids) # 重複を許さず、出現順を保持するために OrderedDict を使用
    print(f"抽出された PMID (重複除去・順序保持): {list(pmids.keys())}")
    return list(pmids.keys())

def fetch_pubmed_details(pmids):
    """PubMed API を使用して PMID リストに対応する論文詳細を取得する"""
    if not pmids:
        return {}, [] # 詳細と見つからなかったPMIDリストを返す

    details = {}
    not_found_pmids = [] # 見つからなかったPMIDを格納するリスト
    pmid_string = ','.join(pmids)
    url = f"{PUBMED_API_BASE_URL}esummary.fcgi?db=pubmed&id={pmid_string}&retmode=json"

    print(f"PubMed API にリクエスト中: {url}")
    try:
        response = requests.get(url)
        response.raise_for_status() # HTTP エラーがあれば例外を発生させる
        data = response.json()
        print("PubMed API からレスポンスを受信")

        results = data.get('result', {})
        if not results: # 'uids' がなくても results 自体が空なら警告
            print("警告: PubMed API から有効な結果が得られませんでした。")
            # リクエストしたすべてのPMIDが見つからなかったとみなす
            not_found_pmids.extend(pmids)
            return {}, not_found_pmids

        # APIから返されたUIDリスト
        returned_uids = results.get('uids', [])

        # リクエストしたPMIDのうち、API結果に含まれていないものを特定
        requested_pmids_set = set(pmids)
        returned_uids_set = set(returned_uids)
        missing_in_response = list(requested_pmids_set - returned_uids_set)
        if missing_in_response:
            print(f"警告: APIレスポンスに以下のPMIDが含まれていません: {missing_in_response}")
            not_found_pmids.extend(missing_in_response)
            for missing_pmid in missing_in_response:
                 details[missing_pmid] = {'error': 'Not found in API response'}

        # API結果に含まれる各PMIDの詳細を取得
        for pmid in returned_uids:
            if pmid not in results: # results辞書内に詳細がない場合
                print(f"警告: PMID {pmid} の詳細情報が results 内に見つかりません。")
                if pmid not in not_found_pmids:
                    not_found_pmids.append(pmid)
                details[pmid] = {'error': 'Details not found in results dict'}
                continue

            entry = results[pmid]

            # entry に error キーが含まれているかチェック
            if 'error' in entry:
                print(f"警告: PMID {pmid} の詳細取得でAPIエラー: {entry['error']}")
                if pmid not in not_found_pmids: # 重複追加を避ける
                    not_found_pmids.append(pmid)
                # details にはエラー情報を含む entry をそのまま入れるか、別途エラー情報を入れるか選択
                # ここでは entry をそのまま入れる (References 生成時に error をチェックするため)
                details[pmid] = entry
                continue # エラーがあった場合は以降の処理をスキップ

            authors = ', '.join([author['name'] for author in entry.get('authors', [])])
            # 最初の数名の著者のみ表示する場合 (例: 3名まで + et al.)
            # author_list = [author['name'] for author in entry.get('authors', [])]
            # if len(author_list) > 3:
            #     authors = ', '.join(author_list[:3]) + ', et al.'
            # else:
            #     authors = ', '.join(author_list)

            details[pmid] = {
                'authors': authors,
                'year': entry.get('pubdate', '').split(' ')[0], # 年のみ取得
                'title': entry.get('title', 'N/A'),
                'journal': entry.get('source', 'N/A'),
                'volume': entry.get('volume', ''),
                'issue': entry.get('issue', ''),
                'pages': entry.get('pages', ''),
                'pmid': pmid,
                'doi': entry.get('elocationid', '').replace('doi: ', '') if entry.get('elocationid', '').startswith('doi:') else ''
            }
            # API リクエストの間隔を空ける
            time.sleep(API_REQUEST_DELAY)

    except requests.exceptions.RequestException as e:
        print(f"エラー: PubMed API への接続に失敗しました - {e}")
        return {}, [] # エラー時は空の詳細と空のnot_foundリストを返す
    except Exception as e:
        print(f"エラー: PubMed データの処理中に予期せぬエラーが発生しました - {e}")
        return {}, [] # エラー時は空の詳細と空のnot_foundリストを返す

    print(f"取得した論文詳細数: {len(details) - len(not_found_pmids)}") # エラーを除いた数を表示
    if not_found_pmids:
        print(f"見つからなかった、または詳細取得に失敗したPMID数: {len(not_found_pmids)}")
    return details, not_found_pmids # 詳細と見つからなかったPMIDリストを返す

def format_reference_item(details, number, format_string):
    """指定されたフォーマット文字列に従って References の項目を整形する"""
    # 利用可能なプレースホルダーを実際の値で置換
    # 存在しないキーアクセスを防ぐため .get() を使用
    return format_string.format(
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
    ).strip() # 末尾の不要なスペースを削除

def create_references_section(pubmed_details, pmid_to_number_map, format_string, header):
    """References セクションの Markdown 文字列を生成する"""
    if not pubmed_details:
        return ""

    items = []
    # pmid_to_number_map の順序（＝本文中の出現順）でリストを作成
    for pmid, number in pmid_to_number_map.items():
        if pmid in pubmed_details and 'error' not in pubmed_details[pmid]:
            item_str = format_reference_item(pubmed_details[pmid], number, format_string)
            items.append(item_str)
        else:
            # 論文情報が取得できなかった場合の代替表示
            items.append(f"{number}. [PMID {pmid}] - 論文情報の取得に失敗しました。")

    # ヘッダーレベルを動的に設定
    # header は '#' * level + ' References' のような形式で渡される想定
    # ヘッダーとリストの間に空行を挿入 (\n\n)
    return "\n\n" + header + "\n\n" + "\n".join(items)

def detect_header_level(markdown_content):
    """Markdownコンテンツから主要セクションのヘッダーレベルを検出する"""
    # 一般的なセクション名を正規表現で検索 (大文字小文字を区別しない)
    matches = re.findall(r'^(#+)\s+(Introduction|Methods|Results|Discussion|Conclusion|Background|Case Report|Abstract)', markdown_content, re.MULTILINE | re.IGNORECASE)
    if matches:
        # 最初に見つかった主要セクションのレベルを使用
        level = len(matches[0][0])
        print(f"主要セクションのヘッダーレベル {level} を検出しました。")
        return level
    else:
        # 主要セクションが見つからない場合はデフォルトレベル (例: 2) を返す
        print("主要セクションが見つかりませんでした。デフォルトのヘッダーレベル 2 を使用します。")
        return 2

def replace_citations(markdown_content, pmid_to_number_map, format_string):
    """Markdown コンテンツ内の [PMID xxxxx] を指定された形式に置換する"""
    output_content = markdown_content

    # pmid_to_number_map を使って置換
    for pmid, number in pmid_to_number_map.items():
        # 引用形式をフォーマット
        # この例では単純な番号だが、著者名など他の情報も利用可能にする場合は fetch_pubmed_details の結果も渡す必要がある
        citation_replace_str = format_string.format(number=number)
        # PMID 形式の引用 [PMID xxxxx] を置換
        # re.escape で特殊文字をエスケープし、確実な置換を行う
        output_content = re.sub(r'\[PMID\s+' + re.escape(pmid) + r'\]', citation_replace_str, output_content)

    return output_content

def process_markdown_file(input_filepath, output_filepath):
    """Markdown ファイルを処理して引用を置換し、References を追加する"""
    print(f"処理開始: {input_filepath}")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"エラー: 入力ファイルが見つかりません - {input_filepath}")
        return
    except Exception as e:
        print(f"エラー: ファイル読み込み中にエラーが発生しました - {e}")
        return

    # 1. PMID を抽出
    pmids = extract_pmids(content)
    if not pmids:
        print("PMID 形式の引用が見つかりませんでした。処理を終了します。")
        # PMID がなくてもファイルコピーは行う場合
        # try:
        #     with open(output_filepath, 'w', encoding='utf-8') as f:
        #         f.write(content)
        #     print(f"PMID が見つからなかったため、内容は変更せずに出力ファイルにコピーしました: {output_filepath}")
        # except Exception as e:
        #     print(f"エラー: ファイル書き込み中にエラーが発生しました - {e}")
        return

    # 2. PubMed から詳細を取得し、見つからなかったPMIDリストも受け取る
    pubmed_details, not_found_pmids = fetch_pubmed_details(pmids)

    # 取得できた詳細がない場合 (not_found_pmids は関係なく)
    # pubmed_details にはエラー情報が入っている可能性があるので、エラー以外の有効な情報があるかチェック
    has_valid_details = any('error' not in detail for detail in pubmed_details.values())
    if not has_valid_details:
        print("PubMed から有効な論文情報を取得できませんでした。References は生成されません。")
        # ここで処理を中断するか、引用置換だけ行うか選択可能
        # return # 中断する場合

    # 3. PMID と連番のマッピングを作成 (出現順)
    #   Referencesリスト生成時にAPIエラーをチェックするため、ここでは元のpmidsリストでマッピングを作成
    pmid_to_number_map = {pmid: i + 1 for i, pmid in enumerate(pmids)}
    print(f"PMID と番号のマッピング: {pmid_to_number_map}")

    # 4. 本文中の引用を置換 (単一のマッピングを使用)
    modified_content = replace_citations(content, pmid_to_number_map, CITATION_FORMAT)
    print("本文中の引用を置換しました。")

    # 5. ヘッダーレベルを検出
    header_level = detect_header_level(content) # 元のコンテンツから検出
    dynamic_references_header = '#' * header_level + ' References' # ヘッダー文字列を生成

    # 6. References セクションを作成 (単一のマッピングを使用)
    references_section = create_references_section(pubmed_details, pmid_to_number_map, REFERENCE_ITEM_FORMAT, dynamic_references_header)
    if references_section:
        # 有効な文献があるかどうかのチェックは create_references_section 内で行われるため、ここでは単純に表示
        print(f"ヘッダーレベル {header_level} で References セクションを生成しました。")
    else:
        print("References セクションは生成されませんでした。")

    # 7. 最終的な Markdown コンテンツを結合
    # 既存の References セクションがあれば削除または上書きする試み
    # 大文字小文字を区別せず、セクション全体を削除
    modified_content_no_refs = re.sub(r'\n\n#+\s+References\s*\n.*', '', modified_content, flags=re.DOTALL | re.IGNORECASE)
    final_content = modified_content_no_refs.rstrip() + references_section # 末尾の空白を削除してから結合

    # 8. 結果をファイルに書き込み
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print(f"処理完了。結果をファイルに出力しました: {output_filepath}")
    except Exception as e:
        print(f"エラー: ファイル書き込み中にエラーが発生しました - {e}")

# --- ファイル選択ダイアログ関数 ---
def ask_for_file():
    """ファイル選択ダイアログを表示してファイルパスを取得する"""
    root = tk.Tk()
    root.withdraw() # メインウィンドウを表示しない
    filepath = filedialog.askopenfilename(
        title="Markdown ファイルを選択してください",
        filetypes=[("Markdown files", "*.md"), ("All files", "*.*")]
    )
    # ダイアログが閉じられた後に Tkinter ルートウィンドウを破棄
    # ファイルが選択されなかった場合 filepath は空文字列 '' になる
    root.destroy()
    if not filepath:
        print("ファイルが選択されませんでした。")
        return None
    return filepath

# --- メイン処理 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Markdown ファイル内の PubMed 引用を処理し、References リストを生成・置換します。')
    # input_file をオプション引数に変更し、指定がない場合は None になるようにする
    parser.add_argument('input_file', nargs='?', default=None, help='処理対象の Markdown ファイルパス (省略時はダイアログ表示)')
    parser.add_argument('-o', '--output_file', help='出力先のファイルパス (指定しない場合は input_file に _cited を付与)')
    # --- カスタマイズ用引数を追加 ---
    parser.add_argument('--citation-format', default=CITATION_FORMAT,
                        help=f'本文中の引用形式のフォーマット文字列 (デフォルト: "{CITATION_FORMAT}")')
    parser.add_argument('--ref-item-format', default=REFERENCE_ITEM_FORMAT,
                        help=f'References の各項目形式のフォーマット文字列 (デフォルト: "{REFERENCE_ITEM_FORMAT}")')
    # --ref-header 引数は動的生成のため削除
    # parser.add_argument('--ref-header', default=REFERENCES_HEADER, help='...')
    parser.add_argument('--api-delay', type=float, default=API_REQUEST_DELAY,
                        help=f'PubMed API へのリクエスト間隔 (秒) (デフォルト: {API_REQUEST_DELAY})')

    args = parser.parse_args()

    # 入力ファイルが指定されていない場合はダイアログを表示
    input_filepath = args.input_file
    if input_filepath is None:
        print("入力ファイルが指定されていません。ファイル選択ダイアログを開きます。")
        input_filepath = ask_for_file()
        if input_filepath is None:
            # ファイルが選択されなかった場合は終了
            print("処理をキャンセルしました。")
            exit() # または適切なエラー処理

    # 出力ファイルパスが指定されていない場合のデフォルト設定
    output_filepath = args.output_file
    if not output_filepath:
        # input_filepath が None でないことを確認してから splitext を使用
        if input_filepath:
            base, ext = os.path.splitext(input_filepath)
            output_filepath = f"{base}_cited{ext}"
        else:
            # このケースは input_filepath is None で exit しているため通常到達しないはずだが念のため
            print("エラー: 入力ファイルが決定できず、出力ファイル名も指定されていません。")
            exit()

    # グローバル変数をコマンドライン引数で上書き
    CITATION_FORMAT = args.citation_format
    REFERENCE_ITEM_FORMAT = args.ref_item_format
    API_REQUEST_DELAY = args.api_delay

    # process_markdown_file を呼び出す
    process_markdown_file(input_filepath, output_filepath)
