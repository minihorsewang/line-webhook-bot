import os
import json
import time
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# =========================
# LINE 設定
# =========================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# =========================
# Google Sheets 初始化（只跑一次）
# =========================
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")

credentials_info = json.loads(GOOGLE_CREDENTIALS)

credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

service = build("sheets", "v4", credentials=credentials)

# =========================
# 關鍵字快取機制
# =========================
keyword_cache = []
last_refresh_time = 0
CACHE_SECONDS = 60  # 每 60 秒更新一次


def refresh_keyword_rules():
    global keyword_cache, last_refresh_time

    result = service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Sheet1!A:D"
    ).execute()

    values = result.get("values", [])

    rules = []

    for row in values[1:]:
        if len(row) >= 4:
            try:
                priority = int(row[0])
            except:
                priority = 999

            must_include = row[1] if len(row) > 1 else ""
            any_include = row[2] if len(row) > 2 else ""
            reply = row[3]

            rules.append({
                "priority": priority,
                "must": must_include,
                "any": any_include,
                "reply": reply
            })

    rules.sort(key=lambda x: x["priority"])

    keyword_cache = rules
    last_refresh_time = time.time()


def get_keyword_rules():
    global last_refresh_time

    # 如果超過 CACHE_SECONDS 才重新抓
    if time.time() - last_refresh_time > CACHE_SECONDS:
        refresh_keyword_rules()

    return keyword_cache


# =========================
# 未命中紀錄
# =========================
def log_unmatched(user_id, message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    service.spreadsheets().values().append(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Sheet2!A:C",
        valueInputOption="USER_ENTERED",
        body={
            "values": [[now, user_id, message]]
        }
    ).execute()


# =========================
# Webhook
# =========================
@app.route("/callback", methods=["POST", "GET"])
def callback():
    if request.method == "GET":
        return "OK"

    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip().lower()
    user_id = event.source.user_id

    rules = get_keyword_rules()

    for rule in rules:

        # ===== AND 條件 =====
        must_keywords = [
            k.strip().lower()
            for k in rule["must"].split("&")
            if k.strip()
        ]

        must_match = True
        if must_keywords:
            must_match = all(k in user_text for k in must_keywords)

        # ===== OR 條件 =====
        any_keywords = [
            k.strip().lower()
            for k in rule["any"].split("|")
            if k.strip()
        ]

        any_match = False
        if any_keywords:
            any_match = any(k in user_text for k in any_keywords)

        # ===== 判斷 =====
        if must_keywords and any_keywords:
            if must_match and any_match:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=rule["reply"])
                )
                return

        elif must_keywords:
            if must_match:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=rule["reply"])
                )
                return

        elif any_keywords:
            if any_match:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=rule["reply"])
                )
                return

    # 沒命中 → 記錄
    log_unmatched(user_id, user_text)


# 啟動時先載入一次
refresh_keyword_rules()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
