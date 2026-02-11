import os
import json
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


def get_sheet_data():
    # 防呆：如果沒設環境變數就不讀
    if not GOOGLE_CREDENTIALS or not GOOGLE_SHEET_ID:
        print("❌ Google 環境變數未設定")
        return []

    try:
        credentials_info = json.loads(GOOGLE_CREDENTIALS)

        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )

        service = build("sheets", "v4", credentials=credentials)

        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="A:B"
        ).execute()

        values = result.get("values", [])
        return values

    except Exception as e:
        print("❌ 讀取 Google Sheet 失敗:", e)
        return []


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

    sheet_data = get_sheet_data()

    # 🔥 有命中才回，沒有就不回
    for row in sheet_data[1:]:  # 跳過標題列
        if len(row) >= 2:
            keyword = row[0].strip()
            reply = row[1].strip()

            if keyword and keyword in user_text:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply)
                )
                return  # 命中就結束

    # ❌ 沒命中 → 什麼都不做
    return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
