from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ⚠️ 換成你自己的
LINE_CHANNEL_ACCESS_TOKEN = "y/e8n4YZbGqYQz4gzaGr8kq8UyG+4opkRCA5WrrgEC6HwXX+FN9bsYUZ39IfPFt9Bwynvp/cL9EDSMHO2y/Y+lxCGX8HLOipbQ3aiggd5HqVEOoNmRqOXCDa9WusSehDB31TMlBdpBTQZq/z5rZddgdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "49ee8607970925e94bccb13679c435c6"

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# 🔥 這裡就是「回傳文字」的地方
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"我收到你的訊息：{user_text}")
    )

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

