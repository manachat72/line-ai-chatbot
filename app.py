from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai
import os

app = Flask(__name__)

# --- 1. ตั้งค่ากุญแจ (ใส่ Key ของคุณตรงนี้) ---
# อย่าลืม! เอาเครื่องหมาย ' ' ครอบรหัสไว้ด้วยนะครับ
LINE_ACCESS_TOKEN = 'dc2Kj2VlvEtlq/PUVw0O66R2PddrclTlljAy+IB79nfxjJQIkf03HfsLkpVCR82z6sDQ3w9tbFyCk7HHByhpVNMDevVtwdV3HO1+sgP3XUA6la1R3NkDAttp9Gn7e6RLTHRf6lKsDHWE4aYiq2RcZQdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'A81790990BA1D3C3710A897424A2F4EB'
GEMINI_API_KEY = 'AIzaSyAxHWcJMqhTcQFmLCDhd8G8D-3pE1KU8Mg'

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ตั้งค่า Gemini
genai.configure(api_key=GEMINI_API_KEY)
# เลือกรุ่นสมอง (Flash เร็วและฟรี)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 2. พื้นที่ "สอน" บอท (Prompt) ---
# แก้ไขนิสัยบอทตรงนี้ได้เลยครับ
BOT_PERSONA = """
คุณคือผู้ช่วยอัจฉริยะชื่อ 'จาวิส'
- นิสัย: สุภาพ, มีอารมณ์ขันเล็กน้อย, และมีความรู้รอบตัวสูง
- หน้าที่: ตอบคำถามและช่วยเหลือผู้ใช้งานอย่างเต็มที่
- ถ้าไม่รู้คำตอบ: ให้ตอบว่า 'ขออภัยครับ เรื่องนี้ผมยังไม่มีข้อมูล'
- ตอบสั้นกระชับ ไม่เยิ่นเย้อ
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
        # รวมคำสั่งสอน (Persona) เข้ากับข้อความลูกค้า
        prompt = BOT_PERSONA + "\n\nคำถามจากผู้ใช้: " + user_text
        
        # ส่งไปให้ Gemini คิด
        response = model.generate_content(prompt)
        ai_reply = response.text
        
    except Exception as e:
        ai_reply = "ขออภัยครับ ระบบประมวลผลขัดข้องชั่วคราว"
        print(f"Error: {e}")

    # ส่งคำตอบกลับเข้า LINE
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=ai_reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
