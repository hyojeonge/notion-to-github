import os
import requests
import re
import shutil
from datetime import datetime, timezone, timedelta

# [사용자 설정]
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
        else: break
    return results

def get_db_table_md(db_id):
    """하위 데이터베이스의 내용을 마크다운 표로 변환"""
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(url, headers=headers).json()
    pages = res.get('results', [])
    if not pages: return "\n*(데이터베이스가 비어있음)*\n"

    # 헤더 추출
    sample_props = pages[0]['properties']
    cols = [k for k in sample_props.keys()]
    md = "| " + " | ".join(cols) + " |\n"
    md += "| " + " | ".join(["---"] * len(cols)) + " |\n"
    
    for p in pages:
        row = []
        for c in cols:
            prop = p['properties'].get(c, {})
            p_type = prop.get('type')
            txt = ""
            if p_type == 'title' and prop['title']: txt = prop['title'][0]['plain_text']
            elif p_type == 'rich_text' and prop['rich_text']: txt = prop['rich_text'][0]['plain_text']
            elif p_type == 'select' and prop['select']: txt = prop['select']['name']
            elif p_type == 'date' and prop['date']: txt = prop['date']['start']
            row.append(txt.replace("|", "\\|"))
        md += "| " + " | ".join(row) + " |\n"
    return "\n" + md + "\n"

def block_to_md(block, depth=0):
    b_type = block['type']
    data = block.get(b_type, {})
    md = ""
    indent = "  " * depth

    if 'rich_text' in data:
        text = "".join([t.get('plain_text', '') for t in data['rich_text']])
        if b_type == 'paragraph': md = f"{text}\n\n"
        elif b_type.startswith('heading_'):
            level = min(int(b_type.split('_')[1]) + depth, 6)
            md = f"{'#' * level} {text}\n\n"
        elif b_type.endswith('list_item'): md = f"{indent}- {text}\n"
    
    elif b_type == 'child_page':
        md = f"\n{indent}---\n{indent}### 📄 하위 페이지: {data.get('title')}\n"
        for b in get_blocks(block['id']): md += block_to_md(b, depth + 1)
        
    elif b_type == 'child_database':
        md = f"\n{indent}#### 📊 내부 데이터베이스: {data.get('title')}\n"
        md += get_db_table_md(block['id'])

    elif b_type == 'code':
        txt = "".join([t.get('plain_text', '') for t in data.get('rich_text', [])])
        md = f"```{data.get('language', 'text')}\n{txt}\n```\n\n"
    
    elif b_type == 'divider': md = "---\n\n"
    return md

def main():
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    reset_mode = os.environ.get('RESET_MODE', 'false').lower()
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    # [1] RESET 로직
    if reset_mode == 'true':
        if os.path.exists(SAVE_DIR_ROOT): shutil.rmtree(SAVE_DIR_ROOT)
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 📝 My TIL Collection\n\n## 📚 글 목록\n{MARKER_START}\n{MARKER_END}\n")

    # [2] 노션 데이터 쿼리
    payload = {} if fetch_mode == "ALL" else {"filter": {"property": NOTION_PROPERTY_DATE, "date": {"equals": today}}}
    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers, json=payload).json()
    pages = res.get('results', [])

    if not pages:
        print(">> 조회된 페이지가 없습니다. ID나 권한을 확인하세요.")
        return

    for p in pages:
        props = p['properties']
        title = "제목없음"
        for k in [NOTION_PROPERTY_TITLE, "이름", "제목"]:
            if k in props and props[k]['title']:
                title = props[k]['title'][0]['plain_text']
                break
        
        p_date = props.get(NOTION_PROPERTY_DATE, {}).get('date', {}).get('start', today)
        dir_path = f"{SAVE_DIR_ROOT}/{p_date[:4]}/{p_date[5:7]}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/{p_date}_{title.replace(' ', '_')}.md"

        print(f">> [추출 중] {title}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> 날짜: {p_date}\n\n---\n\n")
            for b in get_blocks(p['id']): f.write(block_to_md(b))

    # [3] README.md 업데이트
    all_files = []
    for r, _, fs in os.walk(SAVE_DIR_ROOT):
        for f in fs:
            if f.endswith(".md"):
                all_files.append({"date": f[:10], "title": f[11:-3].replace("_", " "), "path": os.path.join(r, f).replace("\\", "/")})
    
    all_files.sort(key=lambda x: x['date'], reverse=True)
    table_md = "| 날짜 | 제목 | 바로가기 |\n| :--- | :--- | :--- |\n"
    for i in all_files: table_md += f"| {i['date']} | {i['title']} | [파일 보기](./{i['path']}) |\n"

    with open(README_FILE, "r", encoding="utf-8") as f: content = f.read()
    start, end = content.find(MARKER_START), content.find(MARKER_END)
    if start != -1 and end != -1:
        new_content = content[:start+len(MARKER_START)] + "\n\n" + table_md + "\n" + content[end:]
        with open(README_FILE, "w", encoding="utf-8") as f: f.write(new_content)
    print(">> 모든 작업 완료!")

if __name__ == "__main__":
    main()
