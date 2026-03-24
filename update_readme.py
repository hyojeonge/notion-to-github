import os, requests, re, shutil
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
        if res.get('has_more'): url = f"https://api.notion.com/v1/blocks/{block_id}/children?start_cursor={res.get('next_cursor')}"
        else: break
    return results

def main():
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    # [단계 1] 노션 데이터 수집
    res = requests.post(f"https://api.notion.com/v1/databases/{DATABASE_ID}/query", headers=headers).json()
    pages = res.get('results', [])
    
    for p in pages:
        props = p['properties']
        title = props['이름']['title'][0]['plain_text'] if props['이름']['title'] else "제목없음"
        p_date = props.get('날짜', {}).get('date', {}).get('start', today)
        path = f"{SAVE_DIR_ROOT}/{p_date[:4]}/{p_date[5:7]}"
        os.makedirs(path, exist_ok=True)
        
        # 개별 문서 생성
        with open(f"{path}/{p_date}_{title.replace(' ', '_')}.md", "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n> 날짜: {p_date}\n\n---\n\n(내용 업데이트 중...)\n")

    # [단계 2] README 표 데이터 생성
    files = []
    for r, _, fs in os.walk(SAVE_DIR_ROOT):
        for f in fs:
            if f.endswith(".md"):
                files.append(f"| {f[:10]} | {f[11:-3].replace('_', ' ')} | [보러가기](./{os.path.join(r, f).replace('\\', '/')}) |")
    files.sort(reverse=True)
    table_content = "| 날짜 | 제목 | 링크 |\n| :--- | :--- | :--- |\n" + "\n".join(files)

    # [단계 3] README.md 강제 새로 쓰기 (중복 원천 차단)
    # 기존 내용을 무시하고 새 구조로 덮어버립니다.
    new_readme = f"""# 📝 My TIL Collection

## 📚 글 목록

{MARKER_START}

{table_content}

{MARKER_END}
"""
    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(new_readme)
    print(">> README.md가 강제로 재생성되었습니다.")

if __name__ == "__main__":
    main()
