import os
import pandas as pd
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 🔥 讀取 Excel 關鍵字
def load_keywords():
    df = pd.read_excel("keywords.xlsx")
    keyword_dict = {}

    for index, row in df.iterrows():
        keyword = str(row["keyword"])
        reply = str(row["reply"])
        keyword_dict[keyword] = reply

    return keyword_dict


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
    user_text = event.message.text

    keyword_dict = load_keywords()

    reply_text = "不好意思，目前沒有相關資訊。"

    for keyword, reply in keyword_dict.items():
        if keyword in user_text:
            reply_text = reply
            break

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
