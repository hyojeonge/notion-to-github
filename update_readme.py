import os
import requests
import re
from datetime import datetime, timezone, timedelta

# [설정]
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

def get_page_blocks(block_id):
    """하위 블록들을 재귀적으로 가져오지는 않지만, 기본 블록들은 모두 가져옵니다."""
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    results = []
    query_url = url
    while query_url:
        res = requests.get(query_url, headers=headers).json()
        results.extend(res.get('results', []))
        if res.get('has_more'):
            query_url = f"{url}?start_cursor={res.get('next_cursor')}"
        else:
            query_url = None
    return results

def extract_rich_text(rich_text_list):
    """텍스트 안의 서식(굵게, 링크 등)을 마크다운으로 변환합니다."""
    result = ""
    for text in rich_text_list:
        plain = text.get('plain_text', '')
        href = text.get('href')
        if href:
            result += f"[{plain}]({href})"
        else:
            result += plain
    return result

def block_to_markdown(block):
    """노션 블록을 마크다운 문법으로 변환합니다."""
    b_type = block['type']
    data = block.get(b_type, {})
    rich_text = data.get('rich_text', [])
    content = extract_rich_text(rich_text)

    if b_type == 'paragraph': return f"{content}\n\n"
    if b_type == 'heading_1': return f"# {content}\n\n"
    if b_type == 'heading_2': return f"## {content}\n\n"
    if b_type == 'heading_3': return f"### {content}\n\n"
    if b_type == 'bulleted_list_item': return f"- {content}\n"
    if b_type == 'numbered_list_item': return f"1. {content}\n"
    if b_type == 'to_do':
        check = "[x]" if data.get('checked') else "[ ]"
        return f"- {check} {content}\n"
    if b_type == 'code':
        lang = data.get('language', 'text')
        return f"```{lang}\n{content}\n```\n\n"
    if b_type == 'quote': return f"> {content}\n\n"
    if b_type == 'divider': return "---\n\n"
    if b_type == 'image':
        url = data.get('file', {}).get('url') or data.get('external', {}).get('url', '')
        return f"![Image]({url})\n\n"
    return ""

def save_markdown(page, date_str):
    props = page['properties']
    title = "제목없음"
    for key in [NOTION_PROPERTY_TITLE, "이름", "제목"]:
        if key in props and props[key]['title']:
            title = props[key]['title'][0]['text']['content']
            break
            
    # 폴더 구조: TIL/2026/03
    directory = f"{SAVE_DIR_ROOT}/{date_str[:4]}/{date_str[5:7]}"
    os.makedirs(directory, exist_ok=True)
    
    safe_title = re.sub(r'[\\/*?:"<>|]', '', title).replace(' ', '_')
    filename = f"{directory}/{date_str}_{safe_title}.md"
    
    print(f">> [작업중] {title} 내용 추출 시작...")
    blocks = get_page_blocks(page['id'])
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n> 날짜: {date_str}\n> 원본 노션: [링크]({page['url']})\n\n---\n\n")
        if not blocks:
            f.write("\n*(내용이 비어있거나 읽어올 수 없는 블록입니다)*\n")
        for block in blocks:
            f.write(block_to_markdown(block))
    
    return title, filename

def main():
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")
    
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {} if fetch_mode == "ALL" else {"filter": {"property": NOTION_PROPERTY_DATE, "date": {"equals": today}}}

    res = requests.post(url, headers=headers, json=payload).json()
    pages = res.get('results', [])
    
    if not pages:
        print(">> 조회된 데이터가 없습니다.")
        return

    for page in pages:
        date_info = page['properties'].get(NOTION_PROPERTY_DATE, {}).get('date')
        page_date = date_info['start'] if date_info else today
        title, path = save_markdown(page, page_date)
        print(f"DEBUG: 저장 완료 -> {title}")

    # README 업데이트 로직 (생략 - 위와 동일)
    file_list = []
    for root, _, files in os.walk(SAVE_DIR_ROOT):
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(root, f).replace("\\", "/")
                file_list.append(f"- [{f[:10]} : {f[11:-3].replace('_',' ')}](./{p})\n")
    
    file_list.sort(reverse=True)
    with open(README_FILE, "r", encoding="utf-8") as f: content = f.read()
    start, end = content.find(MARKER_START), content.find(MARKER_END)
    if start != -1 and end != -1:
        new_content = content[:start+len(MARKER_START)] + "\n" + "".join(file_list) + content[end:]
        with open(README_FILE, "w", encoding="utf-8") as f: f.write(new_content)

if __name__ == "__main__":
    main()
