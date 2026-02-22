import os
import json
import time
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextSendMessage
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# =========================================
# 環境變數
# =========================================
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

LINE1_SECRET = os.environ.get("LINE1_CHANNEL_SECRET")
LINE1_TOKEN = os.environ.get("LINE1_CHANNEL_ACCESS_TOKEN")
LINE1_SHEET = os.environ.get("LINE1_SHEET_ID")

LINE2_SECRET = os.environ.get("LINE2_CHANNEL_SECRET")
LINE2_TOKEN = os.environ.get("LINE2_CHANNEL_ACCESS_TOKEN")
LINE2_SHEET = os.environ.get("LINE2_SHEET_ID")

# =========================================
# Google 初始化（只跑一次）
# =========================================
credentials_info = json.loads(GOOGLE_CREDENTIALS)

credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

service = build("sheets", "v4", credentials=credentials)

# =========================================
# 快取機制（每個 Sheet 各自快取）
# =========================================
CACHE_SECONDS = 60
sheet_cache = {}  # {sheet_id: {"rules": [], "time": timestamp}}

def refresh_rules(sheet_id):
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
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

            rules.append({
                "priority": priority,
                "must": row[1] if len(row) > 1 else "",
                "any": row[2] if len(row) > 2 else "",
                "reply": row[3]
            })

    rules.sort(key=lambda x: x["priority"])

    sheet_cache[sheet_id] = {
        "rules": rules,
        "time": time.time()
    }

def get_rules(sheet_id):
    if (
        sheet_id not in sheet_cache
        or time.time() - sheet_cache[sheet_id]["time"] > CACHE_SECONDS
    ):
        refresh_rules(sheet_id)

    return sheet_cache[sheet_id]["rules"]

# =========================================
# 未命中紀錄
# =========================================
def log_unmatched(sheet_id, user_id, message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sheet2!A:C",
        valueInputOption="USER_ENTERED",
        body={
            "values": [[now, user_id, message]]
        }
    ).execute()

# =========================================
# 關鍵字比對
# =========================================
def match_rules(user_text, rules):
    user_text = user_text.lower()

    for rule in rules:

        must_keywords = [
            k.strip().lower()
            for k in rule["must"].split("&")
            if k.strip()
        ]

        any_keywords = [
            k.strip().lower()
            for k in rule["any"].split("|")
            if k.strip()
        ]

        must_match = all(k in user_text for k in must_keywords) if must_keywords else False
        any_match = any(k in user_text for k in any_keywords) if any_keywords else False

        if must_keywords and any_keywords:
            if must_match and any_match:
                return rule["reply"]

        elif must_keywords:
            if must_match:
                return rule["reply"]

        elif any_keywords:
            if any_match:
                return rule["reply"]

    return None

# =========================================
# Webhook
# =========================================
@app.route("/callback", methods=["POST"])
def callback():

    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    # 先驗證是哪個 OA（只做驗證，不執行 handler）
    try:
        WebhookHandler(LINE1_SECRET).validate_signature(body, signature)
        current_token = LINE1_TOKEN
        current_sheet = LINE1_SHEET
    except InvalidSignatureError:
        try:
            WebhookHandler(LINE2_SECRET).validate_signature(body, signature)
            current_token = LINE2_TOKEN
            current_sheet = LINE2_SHEET
        except InvalidSignatureError:
            abort(400)

    events = json.loads(body)["events"]

    for event in events:
        if event["type"] == "message" and event["message"]["type"] == "text":

            user_text = event["message"]["text"]
            user_id = event["source"]["userId"]

            rules = get_rules(current_sheet)
            reply = match_rules(user_text, rules)

            line_bot_api = LineBotApi(current_token)

            if reply:
                line_bot_api.reply_message(
                    event["replyToken"],
                    TextSendMessage(text=reply)
                )
            else:
                log_unmatched(current_sheet, user_id, user_text)

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)