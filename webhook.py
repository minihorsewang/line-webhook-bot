import os
import json
import time
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi
from linebot.models import TextSendMessage
from google.oauth2 import service_account
from googleapiclient.discovery import build
from linebot.webhook import WebhookParser
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# =============================
# 環境變數
# =============================
GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS")

LINE1_SECRET = os.environ.get("LINE1_CHANNEL_SECRET")
LINE1_TOKEN = os.environ.get("LINE1_CHANNEL_ACCESS_TOKEN")
LINE1_SHEET = os.environ.get("LINE1_SHEET_ID")

LINE2_SECRET = os.environ.get("LINE2_CHANNEL_SECRET")
LINE2_TOKEN = os.environ.get("LINE2_CHANNEL_ACCESS_TOKEN")
LINE2_SHEET = os.environ.get("LINE2_SHEET_ID")

# =============================
# Google 初始化
# =============================
credentials_info = json.loads(GOOGLE_CREDENTIALS)
credentials = service_account.Credentials.from_service_account_info(
    credentials_info,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
service = build("sheets", "v4", credentials=credentials)

# =============================
# 快取
# =============================
CACHE_SECONDS = 60
sheet_cache = {}

def get_rules(sheet_id):

    if sheet_id not in sheet_cache:
        sheet_cache[sheet_id] = {"rules": [], "time": 0}

    if time.time() - sheet_cache[sheet_id]["time"] < CACHE_SECONDS:
        return sheet_cache[sheet_id]["rules"]

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

    return rules

# =============================
# 比對邏輯
# =============================
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
            for k in rule["any"].split(",")
            if k.strip()
        ]

        # ===== AND 優先 =====
        if must_keywords:
            if all(k in user_text for k in must_keywords):
                return rule["reply"]

        # ===== 如果沒有 AND 才看 OR =====
        elif any_keywords:
            if any(k in user_text for k in any_keywords):
                return rule["reply"]

    return None
# =============================
# Webhook
# =============================
@app.route("/callback", methods=["POST"])
def callback():

    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature")

    # 判斷是哪個 OA
    try:
        parser = WebhookParser(LINE1_SECRET)
        events = parser.parse(body, signature)
        token = LINE1_TOKEN
        sheet = LINE1_SHEET
    except InvalidSignatureError:
        try:
            parser = WebhookParser(LINE2_SECRET)
            events = parser.parse(body, signature)
            token = LINE2_TOKEN
            sheet = LINE2_SHEET
        except:
            abort(400)

    line_bot_api = LineBotApi(token)

    for event in events:
    if event.type == "message" and event.message.type == "text":

        user_text = event.message.text
        user_id = event.source.user_id

        rules = get_rules(sheet)
        reply = match_rules(user_text, rules)

        # ===== 不管命不命中都記錄 =====
        matched = "是" if reply else "否"

        service.spreadsheets().values().append(
            spreadsheetId=sheet,
            range="Sheet2!A:D",
            valueInputOption="USER_ENTERED",
            body={
                "values": [[
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    user_id,
                    user_text,
                    matched
                ]]
            }
        ).execute()

        # ===== 如果有命中才回覆 =====
        if reply:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply)
            )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)