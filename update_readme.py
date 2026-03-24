import os
import requests
import re
import shutil
from datetime import datetime, timezone, timedelta

# [설정 영역]
SAVE_DIR_ROOT = "TIL"
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
    """내부 데이터베이스를 실제 마크다운 표로 변환"""
    try:
        url = f"https://api.notion.com/v1/databases/{db_id}/query"
        res = requests.post(url, headers=headers).json()
        pages = res.get('results', [])
        if not pages: return "\n*(내부 데이터베이스가 비어있음)*\n"

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
                row.append(txt.replace("|", "\\|").replace("\n", " "))
            md += "| " + " | ".join(row) + " |\n"
        return "\n" + md + "\n"
    except:
        return "\n*(데이터베이스를 불러올 수 없습니다. 봇 연결을 확인하세요)*\n"

def block_to_md(block, current_dir, date_str):
    b_type = block['type']
    data = block.get(b_type, {})
    md = ""

    if 'rich_text' in data:
        text = "".join([t.get('plain_text', '') for t in data['rich_text']])
        if b_type == 'paragraph': md = f"{text}\n\n"
        elif b_type.startswith('heading_'):
            level = b_type.split('_')[1]
            md = f"{'#' * int(level)} {text}\n\n"
        elif b_type.endswith('list_item'): md = f"- {text}\n"
    
    elif b_type == 'child_page':
        sub_title = data.get('title', 'Sub_Page')
        safe_name = re.sub(r'[\\/*?:"<>|]', '', sub_title).replace(' ', '_')
        sub_file = f"sub_{date_str}_{safe_name}.md"
        # 하위 페이지를 별도 파일로 생성
        with open(os.path.join(current_dir, sub_file), "w", encoding="utf-8") as f:
            f.write(f"# {sub_title}\n\n> [뒤로 가기](./)\n\n---\n\n")
            for b in get_blocks(block['id']): f.write(block_to_md(b, current_dir, date_str))
        md = f"\n> 📄 **하위 페이지:** [{sub_title}](./{sub_file})\n\n"
        
    elif b_type == 'child_database':
        md = f"\n#### 📊 내부 데이터베이스: {data.get('title')}\n"
        md += get_db_table_md(block['id'])

    elif b_type == 'code':
        txt = "".join([t.get('plain_text', '') for t in data.get('rich_text', [])])
        md = f"```{data.get('language', 'text')}\n{txt}\n```\n\n"
    
    return md

def main():
    reset_mode = os.environ.get('RESET_MODE', 'false').lower()
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    # [1] 강제 초기화 로직: 파일을 읽지 않고 아예 새로 씀 ("w")
    if reset_mode == 'true':
        if os.path.exists(SAVE_DIR_ROOT): shutil.rmtree(SAVE_DIR_ROOT)
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 📝 My TIL Collection\n\n## 📚 글 목록\n{MARKER_START}\n{MARKER_END}\n")
        print(">> README와 TIL 폴더가 초기화되었습니다.")

    # [2] 데이터 수집
    payload = {} if fetch_mode == "ALL" else {"filter": {"property": "날짜", "date": {"equals": today}}}
    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers, json=payload).json()
    
    for p in res.get('results', []):
        props = p['properties']
        title = props['이름']['title'][0]['plain_text'] if props['이름']['title'] else "제목없음"
        p_date = props.get('날짜', {}).get('date', {}).get('start', today)
        
        dir_path = f"{SAVE_DIR_ROOT}/{p_date[:4]}/{p_date[5:7]}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/{p_date}_{title.replace(' ', '_')}.md"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> 날짜: {p_date}\n\n---\n\n")
            for b in get_blocks(p['id']): f.write(block_to_md(b, dir_path, p_date))

    # [3] README 표 업데이트
    all_files = []
    for r, _, fs in os.walk(SAVE_DIR_ROOT):
        for f in fs:
            if f.endswith(".md") and not f.startswith("sub_"):
                all_files.append({"date": f[:10], "title": f[11:-3].replace("_", " "), "path": os.path.join(r, f).replace("\\", "/")})
    
    all_files.sort(key=lambda x: x['date'], reverse=True)
    table_content = "| 날짜 | 제목 | 링크 |\n| :--- | :--- | :--- |\n"
    for i in all_files: table_content += f"| {i['date']} | {i['title']} | [보러가기](./{i['path']}) |\n"

    with open(README_FILE, "r", encoding="utf-8") as f: content = f.read()
    start, end = content.find(MARKER_START), content.find(MARKER_END)
    if start != -1 and end != -1:
        new_readme = content[:start+len(MARKER_START)] + "\n\n" + table_content + "\n" + content[end:]
        with open(README_FILE, "w", encoding="utf-8") as f: f.write(new_readme)

if __name__ == "__main__":
    main()
