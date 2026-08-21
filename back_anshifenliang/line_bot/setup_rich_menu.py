"""
一次性脚本：给 line_bot 创建 v3 版 Rich Menu。

用法（在服务器上、和 line_bot.py 同一个目录、同一个 .env 旁边跑）：
    python3 setup_rich_menu.py

跟 v2 的差异：
    - 图片换成 richmenu.png（LINE 绿 + 白色两个按钮，图标减半）
    - chatBarText（菜单收起时那条常驻横栏的文字）改成繁体「打開選單」

这个脚本只用 .env 里的 token 发请求，不会把 token 打印到任何输出。
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
if not TOKEN or TOKEN == "PLACEHOLDER_REPLACE_ME":
    print("错误：.env 里的 LINE_CHANNEL_ACCESS_TOKEN 还没填真实值，先去配置好再跑这个脚本。")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

RICH_MENU_BODY = {
    "size": {"width": 2500, "height": 843},
    "selected": True,
    "name": "anshifenliang-toggle-v3",
    "chatBarText": "打開選單",
    "areas": [
        {
            "bounds": {"x": 0, "y": 0, "width": 1250, "height": 843},
            "action": {"type": "message", "label": "詩歌查詢", "text": "诗歌"},
        },
        {
            "bounds": {"x": 1250, "y": 0, "width": 1250, "height": 843},
            "action": {"type": "message", "label": "轉人工客服", "text": "人工客服"},
        },
    ],
}

IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "richmenu.png")


def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"错误：找不到菜单图片 {IMAGE_PATH}，确认 richmenu.png 和这个脚本放在同一个目录。")
        sys.exit(1)

    print("1/3 创建 Rich Menu...")
    resp = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS,
        json=RICH_MENU_BODY,
        timeout=15,
    )
    resp.raise_for_status()
    rich_menu_id = resp.json()["richMenuId"]
    print(f"    创建成功，richMenuId = {rich_menu_id}")

    print("2/3 上传菜单图片...")
    with open(IMAGE_PATH, "rb") as f:
        img_resp = requests.post(
            f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "image/png",
            },
            data=f.read(),
            timeout=30,
        )
    img_resp.raise_for_status()
    print("    图片上传成功")

    print("3/3 设为所有用户的默认菜单...")
    default_resp = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
        headers=HEADERS,
        timeout=15,
    )
    default_resp.raise_for_status()
    print("    设置成功")

    print("\n全部完成。")
    print(f"（新 richMenuId：{rich_menu_id}，记下来以后要删除/替换会用到）")


if __name__ == "__main__":
    main()
