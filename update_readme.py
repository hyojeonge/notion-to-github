import os
import requests
import re
import shutil
from datetime import datetime, timezone, timedelta

# [설정]
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
    """내부 데이터베이스 내용을 마크다운 표로 변환"""
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

def block_to_md(block, current_dir, date_str, depth=0):
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
        sub_title = data.get('title', 'Sub_Page')
        safe_name = re.sub(r'[\\/*?:"<>|]', '', sub_title).replace(' ', '_')
        sub_file = f"sub_{date_str}_{safe_name}.md"
        with open(os.path.join(current_dir, sub_file), "w", encoding="utf-8") as f:
            f.write(f"# {sub_title}\n\n> [뒤로 가기](./)\n\n---\n\n")
            for b in get_blocks(block['id']): f.write(block_to_md(b, current_dir, date_str, 0))
        md = f"\n> 📄 **하위 페이지:** [{sub_title}](./{sub_file})\n\n"
        
    elif b_type == 'child_database':
        md = f"\n#### 📊 내부 데이터베이스: {data.get('title')}\n"
        md += get_db_table_md(block['id'])

    elif b_type == 'code':
        txt = "".join([t.get('plain_text', '') for t in data.get('rich_text', [])])
        md = f"```{data.get('language', 'text')}\n{txt}\n```\n\n"
    
    elif b_type == 'divider': md = "---\n\n"
    elif b_type == 'bookmark': md = f"🔗 [북마크]({data.get('url')})\n\n"
    
    return md

def main():
    reset_mode = os.environ.get('RESET_MODE', 'false').lower()
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    # [1] README 및 TIL 폴더 완전 초기화 (RESET_MODE=true 시)
    if reset_mode == 'true':
        print(">> [완전 초기화] README와 TIL 폴더를 새로 생성합니다.")
        if os.path.exists(SAVE_DIR_ROOT): shutil.rmtree(SAVE_DIR_ROOT)
        # README를 덮어쓰기("w")로 새로 생성하여 중복 방지
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 📝 My TIL Collection\n\n노션 연동 TIL 저장소입니다.\n\n## 📚 글 목록\n{MARKER_START}\n{MARKER_END}\n")

    # [2] 노션 데이터 수집 및 개별 파일 생성
    payload = {} if fetch_mode == "ALL" else {"filter": {"property": "날짜", "date": {"equals": today}}}
    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers, json=payload).json()
    
    for p in res.get('results', []):
        props = p['properties']
        title = props['이름']['title'][0]['plain_text'] if props['이름']['title'] else "제목없음"
        p_date = props.get('날짜', {}).get('date', {}).get('start', today)
        dir_path = f"{SAVE_DIR_ROOT}/{p_date[:4]}/{p_date[5:7]}"
        os.makedirs(dir_path, exist_ok=True)
        file_path = f"{dir_path}/{p_date}_{title.replace(' ', '_')}.md"

        print(f">> [작업중] {title}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> 날짜: {p_date}\n\n---\n\n")
            for b in get_blocks(p['id']): f.write(block_to_md(b, dir_path, p_date))

    # [3] README 목록 업데이트
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
