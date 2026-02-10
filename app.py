import os
import psycopg2
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# --- 1. ดึงค่ากุญแจ ---
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# แก้บั๊ก URL ของ Database (แปลง postgres:// เป็น postgresql:// เพื่อความชัวร์)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 2. ตั้งค่า Gemini แบบปิด Safety Filter (สำคัญ!) ---
genai.configure(api_key=GEMINI_API_KEY)

# ตั้งค่าความปลอดภัยเป็น BLOCK_NONE (ปิดการบล็อก)
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    safety_settings=safety_settings
)

# --- 3. ระบบ Database ---
def get_db_connection():
    # เพิ่ม sslmode='require' เพื่อความปลอดภัยและเสถียร
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                message TEXT,
                reply TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database Connected & Initialized!")
    except Exception as e:
        print(f"❌ Init DB Error: {e}")

if DATABASE_URL:
    init_db()

# --- 4. Webhook ---
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
    user_msg = event.message.text
    user_id = event.source.user_id
    
    try:
        # ส่งให้ Gemini คิด
        response = model.generate_content(user_msg)
        
        # เช็คว่ามีคำตอบไหม (กัน Error กรณีโดนบล็อกเงียบๆ)
        if response.text:
            bot_reply = response.text
        else:
            bot_reply = "ขออภัยครับ ฉันนึกคำตอบไม่ออก (No Response)"
            
        # บันทึกลง Database
        if DATABASE_URL:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO chat_history (user_id, message, reply) VALUES (%s, %s, %s)",
                    (user_id, user_msg, bot_reply)
                )
                conn.commit()
                cur.close()
                conn.close()
            except Exception as db_err:
                print(f"❌ Database Save Error: {db_err}")
            
    except Exception as e:
        # ฟ้อง Error เข้าแชทตรงๆ
        bot_reply = f"System Error: {str(e)}"
        print(f"❌ Critical Error: {e}")

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=bot_reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
