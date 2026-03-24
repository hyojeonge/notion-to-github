import os
import requests

# [사용자 설정]
# 깃허브 Secrets에 넣은 ID가 '페이지 ID'라고 가정합니다.
PAGE_ID = os.environ['NOTION_DATABASE_ID'] 
NOTION_TOKEN = os.environ['NOTION_TOKEN']
README_FILE = "README.md"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_blocks(block_id):
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    return requests.get(url, headers=headers).json().get('results', [])

def block_to_md(block):
    # (기존의 block_to_markdown 로직과 동일하지만 페이지 전체를 읽는 방식)
    b_type = block['type']
    if b_type == 'paragraph':
        text = "".join([t['plain_text'] for t in block['paragraph'].get('rich_text', [])])
        return text + "\n\n"
    elif b_type.startswith('heading_'):
        level = b_type.split('_')[1]
        text = "".join([t['plain_text'] for t in block[b_type].get('rich_text', [])])
        return "#" * int(level) + " " + text + "\n\n"
    # ... (필요한 다른 블록 타입들 추가 가능)
    return ""

def main():
    print(f">> 페이지(ID: {PAGE_ID}) 데이터를 읽어옵니다.")
    blocks = get_blocks(PAGE_ID)
    
    if not blocks:
        print(">> [에러] 페이지 내용을 가져오지 못했습니다. 연결(Connection)을 확인하세요.")
        return

    markdown = "# 노션에서 가져온 페이지\n\n"
    for block in blocks:
        markdown += block_to_md(block)

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(">> README.md 업데이트 완료!")

if __name__ == "__main__":
    main()
