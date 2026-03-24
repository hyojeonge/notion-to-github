import os
import requests
import re
import shutil
from datetime import datetime, timezone, timedelta

# [설정 영역]
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
        try:
            res = requests.get(url, headers=headers, params=params).json()
            results.extend(res.get('results', []))
            if res.get('has_more'):
                params['start_cursor'] = res.get('next_cursor')
            else: break
        except: break
    return results

def get_database_contents_as_table(db_id, indent_level=0):
    """하위 데이터베이스의 내용을 마크다운 표 형식 문자열로 반환합니다."""
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(url, headers=headers).json()
    pages = res.get('results', [])
    if not pages: return ""

    # 표 헤더 생성 (첫 페이지의 속성 키들 활용)
    sample_props = pages[0]['properties']
    keys = [k for k in sample_props.keys()]
    header = "| " + " | ".join(keys) + " |\n"
    separator = "| " + " | ".join(["---"] * len(keys)) + " |\n"
    
    rows = ""
    for p in pages:
        row_data = []
        for k in keys:
            prop = p['properties'].get(k, {})
            p_type = prop.get('type')
            val = ""
            if p_type == 'title': val = prop['title'][0]['plain_text'] if prop['title'] else ""
            elif p_type == 'rich_text': val = prop['rich_text'][0]['plain_text'] if prop['rich_text'] else ""
            elif p_type == 'select': val = prop['select']['name'] if prop['select'] else ""
            elif p_type == 'date': val = prop['date']['start'] if prop['date'] else ""
            row_data.append(val.replace("|", "\\|")) # 파이프 문자 이스케이프
        rows += "| " + " | ".join(row_data) + " |\n"
        
        # 하위 데이터베이스 안의 각 페이지 '내용'도 심층 스캔 (선택 사항)
        sub_content = ""
        sub_blocks = get_blocks(p['id'])
        for sb in sub_blocks:
            sub_content += block_to_markdown(sb, indent_level + 1)
        if sub_content.strip():
            rows += f"\n> **{row_data[0]} 상세 내용:**\n{sub_content}\n\n"

    return f"\n{header}{separator}{rows}\n"

def block_to_markdown(block, depth=0):
    b_type = block['type']
    data = block.get(b_type, {})
    md = ""
    indent = "  " * depth

    if 'rich_text' in data:
        text = "".join([t.get('plain_text', '') for t in data['rich_text']])
        if b_type == 'paragraph': md = f"{text}\n\n"
        elif b_type.startswith('heading_'):
            md = f"{'#' * (int(b_type.split('_')[1]) + depth)} {text}\n\n"
        elif b_type.endswith('list_item'):
            md = f"{indent}- {text}\n"

    # [핵심] 하위 페이지 재귀 스캔
    elif b_type == 'child_page':
        md = f"\n{indent}---\n{indent}## 📄 하위 페이지: {data.get('title')}\n"
        for sb in get_blocks(block['id']):
            md += block_to_markdown(sb, depth + 1)

    # [핵심] 하위 데이터베이스를 표 형식으로 변환
    elif b_type == 'child_database':
        md = f"\n{indent}### 📊 내부 데이터베이스: {data.get('title')}\n"
        md += get_database_contents_as_table(block['id'], depth)

    elif b_type == 'code':
        code = "".join([t.get('plain_text', '') for t in data.get('rich_text', [])])
        md = f"```{data.get('language', 'text')}\n{code}\n```\n\n"
    
    return md

def main():
    fetch_mode = os.environ.get('FETCH_MODE', 'DAILY')
    reset_mode = os.environ.get('RESET_MODE', 'false').lower()
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    # 초기화
    if reset_mode == 'true':
        if os.path.exists(SAVE_DIR_ROOT): shutil.rmtree(SAVE_DIR_ROOT)
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 📝 My TIL Collection\n\n## 📚 글 목록\n{MARKER_START}\n{MARKER_END}\n")

    # 데이터 가져오기
    payload = {} if fetch_mode == "ALL" else {"filter": {"property": NOTION_PROPERTY_DATE, "date": {"equals": today}}}
    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers, json=payload).json()
    
    for page in res.get('results', []):
        props = page['properties']
        title = props[NOTION_PROPERTY_TITLE]['title'][0]['plain_text'] if props[NOTION_PROPERTY_TITLE]['title'] else "제목없음"
        p_date = props.get(NOTION_PROPERTY_DATE, {}).get('date', {}).get('start', today)
        
        file_path = f"{SAVE_DIR_ROOT}/{p_date[:7].replace('-','/')}/{p_date}_{title.replace(' ','_')}.md"
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        print(f">> [심층 스캔] {title}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> 날짜: {p_date}\n\n---\n\n")
            for b in get_blocks(page['id']):
                f.write(block_to_markdown(b))

    # README 표 업데이트 (생략 - 이전과 동일한 로직 적용)
    # ... (생략된 부분은 위 답변의 README 업데이트 로직을 그대로 사용하세요)

if __name__ == "__main__":
    main()
