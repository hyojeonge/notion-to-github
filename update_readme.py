import os
import requests
import re
from datetime import datetime, timezone, timedelta

# =======================================================
# [사용자 설정 영역]
# =======================================================
SAVE_DIR_ROOT = "TIL" 
# 노션 열 이름이 '이름'인지 '제목'인지 상관없도록 아래에서 자동 처리합니다.
NOTION_PROPERTY_TITLE = "이름" 
NOTION_PROPERTY_DATE = "날짜"
README_FILE = "README.md"
MARKER_START = ""
MARKER_END = ""
TIMEZONE_HOURS = 9 

DEFAULT_README_TEMPLATE = f"""# 📝 My TIL Collection

노션에서 작성된 TIL(Today I Learned)이 자동으로 업로드되는 저장소입니다.

## 📚 글 목록
{MARKER_START}
{MARKER_END}
"""

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
    response = requests.get(url, headers=headers)
    return response.json().get('results', [])

def extract_text_from_rich_text(rich_text_list):
    content = ""
    for text in rich_text_list:
        plain = text['plain_text']
        href = text.get('href')
        content += f"[{plain}]({href})" if href else plain
    return content

def block_to_markdown(block):
    b_type = block['type']
    if b_type in ['paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item', 'to_do', 'toggle', 'quote', 'callout']:
        rich_text = block[b_type].get('rich_text', [])
        content = extract_text_from_rich_text(rich_text)
        if b_type == 'paragraph': return content + "\n\n"
        elif b_type == 'heading_1': return f"# {content}\n\n"
        elif b_type == 'heading_2': return f"## {content}\n\n"
        elif b_type == 'heading_3': return f"### {content}\n\n"
        elif b_type == 'bulleted_list_item': return f"- {content}\n"
        elif b_type == 'numbered_list_item': return f"1. {content}\n"
        elif b_type == 'to_do':
            checked = "[x]" if block['to_do']['checked'] else "[ ]"
            return f"- {checked} {content}\n"
        elif b_type == 'quote': return f"> {content}\n\n"
        elif b_type == 'callout': return f"> 💡 {content}\n\n"
        elif b_type == 'toggle': return f"- ▶ {content}\n"
    elif b_type == 'code':
        language = block['code'].get('language', 'text')
        content = extract_text_from_rich_text(block['code'].get('rich_text', []))
        return f"```{language}\n{content}\n```\n\n"
    elif b_type == 'image':
        url = block['image'].get('file', {}).get('url') or block['image'].get('external', {}).get('url') or ""
        return f"![Image]({url})\n\n"
    elif b_type == 'divider': return "---\n\n"
    return ""

def sanitize_filename(title):
    clean_name = re.sub(r'[\\/*?:"<>|]', "", title)
    return clean_name.replace(" ", "_")

def save_as_markdown(page, date_str):
    page_id = page['id']
    props = page['properties']
    
    # 제목 추출 로직 강화: '이름' 또는 '제목' 중 존재하는 것을 사용
    title = "제목없음"
    for attr in [NOTION_PROPERTY_TITLE, "이름", "제목", "Name", "Title"]:
        if attr in props and props[attr]['title']:
            title = props[attr]['title'][0]['text']['content']
            break
    
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    year, month = date_obj.strftime("%Y"), date_obj.strftime("%m")
    directory = f"{SAVE_DIR_ROOT}/{year}/{month}"
    os.makedirs(directory, exist_ok=True)
    
    filename = f"{directory}/{date_str}_{sanitize_filename(title)}.md"
    blocks = get_page_blocks(page_id)
    
    markdown_content = f"# {title}\n\n> 날짜: {date_str}\n> 원본 노션: [링크]({page['url']})\n\n---\n\n"
    for block in blocks:
        markdown_content += block_to_markdown(block)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    return title, filename

def update_main_readme_by_scanning(reset_mode):
    if not os.path.exists(SAVE_DIR_ROOT): return
    files_data = []
    for root, _, files in os.walk(SAVE_DIR_ROOT):
        for file in files:
            if file.endswith(".md"):
                path = os.path.join(root, file)
                try:
                    date_obj = datetime.strptime(file[:10], "%Y-%m-%d")
                    files_data.append({"date": date_obj, "date_str": file[:10], "title": file[11:-3].replace("_", " "), "path": path})
                except: continue

    files_data.sort(key=lambda x: x["date"], reverse=True)
    grouped = {}
    for item in files_data:
        m_key = item["date"].strftime("%Y년 %m월")
        if m_key not in grouped: grouped[m_key] = []
        grouped[m_key].append(item)

    new_content = ""
    for i, (month, items) in enumerate(grouped.items()):
        content = f"### {month}\n" if i == 0 else f"<details>\n<summary>{month} ({len(items)}개)</summary>\n\n"
        for item in items:
            content += f"- [{item['date_str']} : {item['title']}](./{item['path'].replace(' ', '%20')})\n"
        new_content += content + ("\n" if i == 0 else "\n</details>\n\n")

    if reset_mode == 'true' or not os.path.exists(README_FILE):
        with open(README_FILE, "w", encoding="utf-8") as f: f.write(DEFAULT_README_TEMPLATE)

    with open(README_FILE, "r", encoding="utf-8") as f: readme_text = f.read()
    start, end = readme_text.find(MARKER_START), readme_text.find(MARKER_END)

    if start == -1 or end == -1:
        final_content = readme_text + f"\n\n{MARKER_START}\n{new_content}{MARKER_END}"
    else:
        final_content = readme_text[:start + len(MARKER_START)] + "\n" + new_content + readme_text[end:]

    with open(README_FILE, "w", encoding="utf-8") as f: f.write(final_content)

def main():
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    reset_mode = os.environ.get('RESET_MODE', 'false').lower()
    kst = timezone(timedelta(hours=TIMEZONE_HOURS))
    today_str = datetime.now(kst).strftime("%Y-%m-%d")
    
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {}
    if fetch_mode != "ALL":
        target_date = (datetime.now(kst) - timedelta(days=1)).strftime("%Y-%m-%d")
        payload["filter"] = {"property": NOTION_PROPERTY_DATE, "date": {"equals": target_date}}

    has_more, next_cursor = True, None
    while has_more:
        if next_cursor: payload['start_cursor'] = next_cursor
        res = requests.post(url, headers=headers, json=payload)
        data = res.json()
        
        pages = data.get('results', [])
        if not pages:
            print(">> [DEBUG] 조회된 페이지가 없습니다. 연결이나 필터를 확인하세요.")
            break

        for page in pages:
            props = page.get('properties', {})
            # 날짜 데이터 추출 (없으면 오늘 날짜로 강제 할당)
            date_info = props.get(NOTION_PROPERTY_DATE, {}).get('date')
            page_date = date_info['start'] if date_info else today_str
            
            title, _ = save_as_markdown(page, page_date)
            print(f"DEBUG: 저장 완료 -> {page_date} : {title}")
        
        has_more, next_cursor = data.get('has_more', False), data.get('next_cursor')

    update_main_readme_by_scanning(reset_mode)

if __name__ == "__main__":
    main()
