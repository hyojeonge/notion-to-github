import os
import requests
import re
from datetime import datetime, timezone, timedelta

# =======================================================
# [사용자 설정 영역]
# =======================================================
SAVE_DIR_ROOT = "TIL" 
NOTION_PROPERTY_TITLE = "이름" # 노션의 첫 번째 열 이름
NOTION_PROPERTY_DATE = "날짜"  # 노션의 날짜 열 이름
README_FILE = "README.md"
MARKER_START = ""
MARKER_END = ""
TIMEZONE_HOURS = 9 

# =======================================================
# [시스템 설정]
# =======================================================
NOTION_TOKEN = os.environ['NOTION_TOKEN']
DATABASE_ID = os.environ['NOTION_DATABASE_ID']

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_page_blocks(page_id):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=headers)
    return res.json().get('results', [])

def extract_text(rich_text_list):
    return "".join([t['plain_text'] for t in rich_text_list])

def block_to_markdown(block):
    b_type = block['type']
    if b_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item']:
        content = extract_text(block[b_type].get('rich_text', []))
        if b_type == 'paragraph': return content + "\n\n"
        if b_type.startswith('heading_'): return "#" * int(b_type[-1]) + " " + content + "\n\n"
        if b_type.endswith('list_item'): return "- " + content + "\n"
    elif b_type == 'code':
        return f"```{block['code'].get('language','text')}\n{extract_text(block['code'].get('rich_text', []))}\n```\n\n"
    return ""

def save_markdown(page, date_str):
    props = page['properties']
    # 제목 찾기 (이름 또는 제목)
    title = "제목없음"
    for key in [NOTION_PROPERTY_TITLE, "이름", "제목"]:
        if key in props and props[key]['title']:
            title = props[key]['title'][0]['text']['content']
            break
            
    directory = f"{SAVE_DIR_ROOT}/{date_str[:7].replace('-','/')}"
    os.makedirs(directory, exist_ok=True)
    filename = f"{directory}/{date_str}_{re.sub(r'[\\/*?:\u0022<>|]', '', title).replace(' ','_')}.md"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n> 날짜: {date_str}\n\n---\n\n")
        for block in get_page_blocks(page['id']):
            f.write(block_to_markdown(block))
    return title, filename

def main():
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    kst = timezone(timedelta(hours=TIMEZONE_HOURS))
    today = datetime.now(kst).strftime("%Y-%m-%d")
    
    payload = {}
    if fetch_mode != "ALL":
        payload["filter"] = {"property": NOTION_PROPERTY_DATE, "date": {"equals": today}}

    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers, json=payload)
    pages = res.json().get('results', [])
    
    if not pages:
        print(">> [확인] 가져올 데이터가 없습니다. 노션의 날짜와 연결을 확인하세요.")
        return

    for page in pages:
        date_info = page['properties'].get(NOTION_PROPERTY_DATE, {}).get('date')
        page_date = date_info['start'] if date_info else today
        title, path = save_markdown(page, page_date)
        print(f"DEBUG: 저장 완료 -> {title} ({path})")

    # README 목록 업데이트
    file_list = []
    for root, _, files in os.walk(SAVE_DIR_ROOT):
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(root, f).replace("\\", "/")
                file_list.append(f"- [{f[:10]} : {f[11:-3].replace('_',' ')}](./{p})\n")
    
    file_list.sort(reverse=True)
    with open(README_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    start, end = content.find(MARKER_START), content.find(MARKER_END)
    if start != -1 and end != -1:
        new_readme = content[:start+len(MARKER_START)] + "\n" + "".join(file_list) + content[end:]
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(new_readme)
    print(">> 모든 작업이 완료되었습니다!")

if __name__ == "__main__":
    main()
