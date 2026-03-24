import os, requests, re, shutil, sys
from datetime import datetime, timezone, timedelta

# [설정]
SAVE_DIR_ROOT = "TIL"
README_FILE = "README.md"
MARKER_START = ""
MARKER_END = ""
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DATABASE_ID = os.environ.get('NOTION_DATABASE_ID')

headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_blocks(block_id):
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    results = []
    while True:
        res = requests.get(url, headers=headers).json()
        results.extend(res.get('results', []))
        if res.get('has_more'): 
            params = {"start_cursor": res.get('next_cursor')}
            res = requests.get(url, headers=headers, params=params).json()
        else: break
    return results

def get_db_table_md(db_id):
    """하위 데이터베이스 내용을 표로 변환"""
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=headers).json()
        pages = res.get('results', [])
        if not pages: 
            print(f">> [INFO] 데이터베이스 {db_id}가 비어있습니다.")
            return "\n*(표 내용 없음)*\n"
        
        cols = list(pages[0]['properties'].keys())
        md = "| " + " | ".join(cols) + " |\n| " + " | ".join(["---"] * len(cols)) + " |\n"
        for p in pages:
            row = []
            for c in cols:
                prop = p['properties'].get(c, {})
                pt = prop.get('type')
                txt = ""
                if pt == 'title' and prop['title']: txt = prop['title'][0]['plain_text']
                elif pt == 'rich_text' and prop['rich_text']: txt = prop['rich_text'][0]['plain_text']
                elif pt == 'select' and prop['select']: txt = prop['select']['name']
                row.append(txt.replace("|", "\\|"))
            md += "| " + " | ".join(row) + " |\n"
        return "\n" + md + "\n"
    except Exception as e:
        print(f">> [ERROR] 하위 데이터베이스 읽기 실패: {e}")
        return "\n*(데이터베이스 읽기 실패: 봇 초대 권한을 확인하세요)*\n"

def block_to_md(block, current_dir, date_str):
    bt = block['type']
    data = block.get(bt, {})
    md = ""
    if 'rich_text' in data:
        text = "".join([t.get('plain_text', '') for t in data['rich_text']])
        if bt == 'paragraph': md = f"{text}\n\n"
        elif bt.startswith('heading_'): md = f"{'#' * int(bt.split('_')[1])} {text}\n\n"
        elif bt.endswith('list_item'): md = f"- {text}\n"
    elif bt == 'child_page':
        name = re.sub(r'[\\/*?:"<>|]', '', data.get('title', 'Sub')).replace(' ', '_')
        sub_file = f"sub_{date_str}_{name}.md"
        sub_path = os.path.join(current_dir, sub_file)
        with open(sub_path, "w", encoding="utf-8") as f:
            f.write(f"# {data.get('title')}\n\n[← 뒤로](./)\n\n---\n\n")
            for b in get_blocks(block['id']): f.write(block_to_md(b, current_dir, date_str))
        md = f"\n> 📄 하위 페이지: [{data.get('title')}](./{sub_file})\n\n"
    elif bt == 'child_database':
        # 하위 데이터베이스 발견 시 표 변환 함수 호출
        md = f"\n#### 📊 {data.get('title')}\n" + get_db_table_md(block['id'])
    elif bt == 'code':
        md = f"```{data.get('language', 'text')}\n" + "".join([t.get('plain_text', '') for t in data.get('rich_text', [])]) + "\n```\n\n"
    return md

def main():
    is_reset = "--reset" in sys.argv
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    # [리셋 로직] README를 아예 새로 만듦
    if is_reset or not os.path.exists(README_FILE):
        print(">> README를 새로 생성합니다.")
        if os.path.exists(SAVE_DIR_ROOT): shutil.rmtree(SAVE_DIR_ROOT)
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 📝 My TIL Collection\n\n## 📚 글 목록\n{MARKER_START}\n{MARKER_END}\n")

    # 노션 쿼리 및 파일 생성
    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers).json()
    for p in res.get('results', []):
        props = p['properties']
        title = props['이름']['title'][0]['plain_text'] if props['이름']['title'] else "No_Title"
        p_date = props.get('날짜', {}).get('date', {}).get('start', today)
        path = f"{SAVE_DIR_ROOT}/{p_date[:4]}/{p_date[5:7]}"
        os.makedirs(path, exist_ok=True)
        
        file_name = f"{p_date}_{title.replace(' ', '_')}.md"
        with open(os.path.join(path, file_name), "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> 날짜: {p_date}\n\n---\n\n")
            for b in get_blocks(p['id']): f.write(block_to_md(b, path, p_date))

    # README 업데이트 (오류 수정됨)
    files_list = []
    for r, _, fs in os.walk(SAVE_DIR_ROOT):
        for f in fs:
            if f.endswith(".md") and not f.startswith("sub_"):
                # 백슬래시를 미리 처리하여 f-string 오류 방지
                rel_path = os.path.join(r, f).replace('\\', '/')
                files_list.append(f"| {f[:10]} | {f[11:-3]} | [보러가기](./{rel_path}) |")
    
    files_list.sort(reverse=True)
    table = "| 날짜 | 제목 | 링크 |\n| :--- | :--- | :--- |\n" + "\n".join(files_list)

    with open(README_FILE, "r", encoding="utf-8") as f: content = f.read()
    start, end = content.find(MARKER_START), content.find(MARKER_END)
    
    if start != -1 and end != -1:
        new_content = content[:start+len(MARKER_START)] + "\n\n" + table + "\n\n" + content[end:]
        with open(README_FILE, "w", encoding="utf-8") as f: f.write(new_content)
        print(">> README 업데이트 완료")

if __name__ == "__main__":
    main()
