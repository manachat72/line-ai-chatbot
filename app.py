import os
import psycopg2
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# --- 1. ตั้งค่ากุญแจ ---
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ✅ ตั้งค่า Gemini โดยไม่ระบุ API version เพื่อให้ Library เลือกตัวที่เหมาะสมที่สุดเอง
genai.configure(api_key=GEMINI_API_KEY)

# ✅ แก้ไขชื่อโมเดลเป็น gemini-1.5-flash เพื่อให้รองรับ generateContent บน Library ใหม่
model = genai.GenerativeModel(model_name="gemini-1.5-flash") 

# --- 2. ระบบ Database ---
def get_db_connection():
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
        print("✅ Database Ready!")
    except Exception as e:
        print(f"❌ Database Init Error: {e}")

if DATABASE_URL:
    init_db()

# --- 3. Webhook ---
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
    bot_reply = "ขออภัย ระบบ AI ขัดข้อง แต่เราได้จดบันทึกข้อความของคุณไว้แล้ว"

    # ✅ STEP 1: บันทึกลง Database ทันที (บันทึกก่อนประมวลผล)
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO chat_history (user_id, message, reply) VALUES (%s, %s, %s)",
                (user_id, user_msg, "AI_ERROR_OR_PENDING")
            )
            conn.commit()
            cur.close()
            conn.close()
            print(f"✅ บันทึกคำขอจาก {user_id} สำเร็จ")
        except Exception as db_err:
            print(f"❌ DB Log Error: {db_err}")

    # ✅ STEP 2: ส่งให้ AI คิด (ใช้ try-except แยกส่วนเพื่อไม่ให้ระบบหลักล่ม)
    try:
        response = model.generate_content(user_msg)
        if response.text:
            bot_reply = response.text
    except Exception as ai_err:
        print(f"⚠️ Gemini Error: {ai_err}") # จะแสดง Error 404 ใน Log ถ้าชื่อรุ่นยังผิดอยู่

    # ✅ STEP 3: ส่งข้อความตอบกลับ
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=bot_reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
