import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# --- 1. ดึงค่ากุญแจจาก Environment Variables (ปลอดภัยกว่าแปะโค้ดตรงๆ) ---
# ต้องตั้งชื่อตัวแปรใน Render ให้ตรงกับในวงเล็บนะครับ
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# ตรวจสอบว่ากุญแจมาครบไหม (เผื่อลืมตั้งค่า)
if not all([LINE_ACCESS_TOKEN, LINE_CHANNEL_SECRET, GEMINI_API_KEY]):
    print("Error: กุญแจ API ไม่ครบ กรุณาเช็ค Environment Variables ใน Render")

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 2. ตั้งค่า Gemini AI ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # รุ่น Flash เร็วและฟรี

# --- 3. บุคลิกของบอท (System Prompt) ---
BOT_PERSONA = """
คุณคือ 'จาวิส' ผู้ช่วย AI อัจฉริยะ
- นิสัย: สุภาพ, เป็นมิตร, ชอบช่วยเหลือ
- หน้าที่: ตอบคำถามผู้ใช้งานอย่างถูกต้องและกระชับ
- ถ้าไม่รู้: ให้ตอบตามตรงว่าไม่ทราบ
"""

@app.route("/callback", methods=['POST'])
def callback():
    # รับ Signature จาก LINE เพื่อยืนยันตัวตน
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
        # รวมคำสั่งบุคลิก + ข้อความลูกค้า
        prompt = f"{BOT_PERSONA}\n\nUser: {user_text}"
        
        # ส่งให้ Gemini คิด
        response = model.generate_content(prompt)
        ai_reply = response.text
        
    except Exception as e:
        ai_reply = "ขออภัยครับ ระบบประมวลผลขัดข้องชั่วคราว"
        print(f"Error: {e}")

    # ส่งข้อความตอบกลับทาง LINE
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=ai_reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
