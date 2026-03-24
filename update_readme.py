import os
import requests
import re
import shutil
from datetime import datetime, timezone, timedelta

# =======================================================
# [사용자 설정 영역]
# =======================================================
SAVE_DIR_ROOT = "TIL"
NOTION_PROPERTY_TITLE = "이름"
NOTION_PROPERTY_DATE = "날짜"
README_FILE = "README.md"
MARKER_START = ""
MARKER_END = ""

NOTION_TOKEN = os.environ['NOTION_TOKEN']
DATABASE_ID = os.environ['NOTION_DATABASE_ID']

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_blocks(block_id):
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    results = []
    params = {}
    while True:
        res = requests.get(url, headers=headers, params=params).json()
        results.extend(res.get('results', []))
        if res.get('has_more'):
            params['start_cursor'] = res.get('next_cursor')
        else:
            break
    return results

def get_database_pages(db_id):
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(url, headers=headers).json()
    return res.get('results', [])

def block_to_markdown(block, depth=0):
    b_type = block['type']
    data = block.get(b_type, {})
    md = ""
    indent = "  " * depth

    # 1. 일반 텍스트 및 헤더 처리
    if 'rich_text' in data:
        text = "".join([t['plain_text'] for t in data['rich_text']])
        if b_type == 'paragraph': md = f"{text}\n\n"
        elif b_type.startswith('heading_'):
            level = b_type.split('_')[1]
            md = f"{'#' * int(level)} {text}\n\n"
        elif b_type.endswith('list_item'):
            md = f"{indent}- {text}\n"

    # 2. [심층 스캔] 하위 페이지(child_page) 처리
    elif b_type == 'child_page':
        page_title = data.get('title', 'Sub Page')
        md = f"\n{indent}--- \n{indent}### 📄 하위 페이지: {page_title}\n"
        sub_blocks = get_blocks(block['id'])
        for sub_block in sub_blocks:
            md += block_to_markdown(sub_block, depth + 1)

    # 3. [심층 스캔] 중첩 데이터베이스(child_database) 처리
    elif b_type == 'child_database':
        db_title = data.get('title', '내부 데이터베이스')
        md = f"\n{indent}> 📊 **{db_title}** (내부 데이터 내용)\n"
        db_pages = get_database_pages(block['id'])
        for p in db_pages:
            p_props = p.get('properties', {})
            # 첫 번째 열(제목) 찾기
            p_title = "제목 없음"
            for k, v in p_props.items():
                if v['type'] == 'title' and v['title']:
                    p_title = v['title'][0]['plain_text']
                    break
            md += f"{indent}> - {p_title}\n"
            # 내부 페이지 내용도 스캔
            sub_p_blocks = get_blocks(p['id'])
            for sb in sub_p_blocks:
                md += block_to_markdown(sb, depth + 2)

    elif b_type == 'code':
        code_text = "".join([t['plain_text'] for t in data.get('rich_text', [])])
        md = f"``` {data.get('language', 'text')}\n{code_text}\n```\n\n"
    
    return md

def main():
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    reset_mode = os.environ.get('RESET_MODE', 'false').lower()
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    # 1. 초기화 (RESET_MODE가 true면 폴더 삭제)
    if reset_mode == 'true' and os.path.exists(SAVE_DIR_ROOT):
        shutil.rmtree(SAVE_DIR_ROOT)
        print(f">> [RESET] {SAVE_DIR_ROOT} 폴더를 초기화했습니다.")

    # 2. 메인 데이터베이스 쿼리
    payload = {} if fetch_mode == "ALL" else {"filter": {"property": NOTION_PROPERTY_DATE, "date": {"equals": today}}}
    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers, json=payload).json()
    pages = res.get('results', [])

    if not pages:
        print(">> 조회된 페이지가 없습니다.")
        return

    for page in pages:
        props = page['properties']
        title = "제목없음"
        for k in [NOTION_PROPERTY_TITLE, "이름", "제목"]:
            if k in props and props[k]['title']:
                title = props[k]['title'][0]['text']['content']
                break
        
        date_info = props.get(NOTION_PROPERTY_DATE, {}).get('date')
        p_date = date_info['start'] if date_info else today
        
        # 파일 저장 경로 설정
        dir_path = f"{SAVE_DIR_ROOT}/{p_date[:4]}/{p_date[5:7]}"
        os.makedirs(dir_path, exist_ok=True)
        safe_title = re.sub(r'[\\/*?:"<>|]', '', title).replace(' ', '_')
        file_path = f"{dir_path}/{p_date}_{safe_title}.md"

        print(f">> [심층 스캔 시작] {title}...")
        blocks = get_blocks(page['id'])
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> 생성일: {p_date}\n\n---\n\n")
            for b in blocks:
                f.write(block_to_markdown(b))
        print(f"DEBUG: {title} 저장 완료")

    # 3. README.md 업데이트 (표 형식으로 UI 개선)
    all_files = []
    for root, _, files in os.walk(SAVE_DIR_ROOT):
        for f in files:
            if f.endswith(".md"):
                path = os.path.join(root, f).replace("\\", "/")
                all_files.append({"date": f[:10], "title": f[11:-3].replace("_", " "), "path": path})
    
    all_files.sort(key=lambda x: x['date'], reverse=True)
    
    table_md = "| 날짜 | 제목 | 바로가기 |\n| :--- | :--- | :--- |\n"
    for item in all_files:
        table_md += f"| {item['date']} | {item['title']} | [파일 보기](./{item['path']}) |\n"

    with open(README_FILE, "r", encoding="utf-8") as f: readme = f.read()
    start, end = readme.find(MARKER_START), readme.find(MARKER_END)
    if start != -1 and end != -1:
        new_readme = readme[:start+len(MARKER_START)] + "\n\n" + table_md + "\n" + readme[end:]
        with open(README_FILE, "w", encoding="utf-8") as f: f.write(new_readme)

if __name__ == "__main__":
    main()
