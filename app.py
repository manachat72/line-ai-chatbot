from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
import os

app = Flask(__name__)

# --- 1. ดึงกุญแจจากหน้าเว็บ Render (Environment Variables) ---
# โค้ดจะไปหยิบค่าที่คุณตั้งไว้ในรูปภาพมาใช้เองอัตโนมัติครับ
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ตั้งค่า Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 2. ข้อความสอนบอท ---
BOT_PERSONA = """
คุณคือผู้ช่วยอัจฉริยะชื่อ 'จาวิส'
- นิสัย: สุภาพ, ร่าเริง, ช่วยเหลือคนเต็มที่
- ถ้าไม่รู้: ให้บอกว่า 'ขออภัยครับ ข้อมูลนี้ผมยังไม่ทราบ'
- ตอบสั้นกระชับ
"""

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    try:
        prompt = BOT_PERSONA + "\n\nคำถาม: " + user_text
        response = model.generate_content(prompt)
        ai_reply = response.text
    except Exception as e:
        ai_reply = "ขออภัยครับ ระบบขัดข้องชั่วคราว"
        print(f"Error: {e}")

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=ai_reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
