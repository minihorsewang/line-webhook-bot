import os
import json
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# ===== LINE 設定 =====
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ===== Google Sheets 設定 =====
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")


def get_service():
    credentials_info = json.loads(GOOGLE_CREDENTIALS)

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )

    service = build("sheets", "v4", credentials=credentials)
    return service


def get_keyword_rules():
    service = get_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Sheet1!A:C"
    ).execute()

    values = result.get("values", [])

    rules = []

    for row in values[1:]:
        if len(row) >= 3:
            priority = int(row[0])
            keywords = [k.strip() for k in row[1].split(",")]
            reply = row[2]

            rules.append({
                "priority": priority,
                "keywords": keywords,
                "reply": reply
            })

    # 按 priority 排序
    rules.sort(key=lambda x: x["priority"])
    return rules


def log_unmatched(user_id, message):
    service = get_service()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    service.spreadsheets().values().append(
        spreadsheetId=GOOGLE_SHEET_ID,
        range="Sheet2!A:C",
        valueInputOption="USER_ENTERED",
        body={
            "values": [[now, user_id, message]]
        }
    ).execute()


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
    user_text = event.message.text.strip()
    user_id = event.source.user_id

    rules = get_keyword_rules()

    for rule in rules:
        for keyword in rule["keywords"]:
            if keyword in user_text:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=rule["reply"])
                )
                return

    # 沒命中 → 記錄
    log_unmatched(user_id, user_text)

    # 不回覆
    return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
