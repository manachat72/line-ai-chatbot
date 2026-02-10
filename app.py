import os
import psycopg2
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

app = Flask(__name__)

# --- 1. ตั้งค่ากุญแจ (Environment Variables) ---
LINE_ACCESS_TOKEN = os.environ.get('LINE_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# แก้บั๊ก URL Database สำหรับ Render
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ตั้งค่า Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# ✅ แก้ไขการเรียกโมเดล: ใช้ชื่อรุ่น gemini-1.5-flash เพื่อเลี่ยง Error 404
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

# --- 3. Webhook Callback ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 4. ฟังก์ชันหลักในการรับและตอบข้อความ ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    user_id = event.source.user_id
    
    # ตั้งค่าเริ่มต้นสำหรับคำตอบกรณีฉุกเฉิน
    bot_reply = "ขณะนี้ระบบ AI ขัดข้อง แต่เราได้รับข้อความของคุณแล้ว"

    # ✅ STEP 1: บันทึกลง Database ทันที (Data Logging ก่อนประมวลผล)
    # เพื่อให้คุณดึงข้อมูลทำ Excel ได้แม้บอทจะตอบไม่ได้
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO chat_history (user_id, message, reply) VALUES (%s, %s, %s)",
                (user_id, user_msg, "Pending/AI_Error") 
            )
            conn.commit()
            cur.close()
            conn.close()
            print(f"✅ บันทึกข้อความจาก {user_id} เรียบร้อย")
        except Exception as db_err:
            print(f"❌ Database Error: {db_err}")

    # ✅ STEP 2: ส่งให้ AI ประมวลผล (แยกส่วนเพื่อกันพัง)
    try:
        # เรียกใช้รุ่นที่ถูกต้องตามคู่มือล่าสุด
        response = model.generate_content(user_msg)
        if response.text:
            bot_reply = response.text
            
            # (ทางเลือก) อัปเดตคำตอบที่ AI คิดได้ลง Database
            if DATABASE_URL:
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE chat_history SET reply = %s WHERE user_id = %s AND message = %s ORDER BY timestamp DESC LIMIT 1",
                        (bot_reply, user_id, user_msg)
                    )
                    conn.commit()
                    cur.close()
                    conn.close()
                except:
                    pass
    except Exception as ai_err:
        # หาก AI พัง (เช่น Error 404) ระบบจะข้ามมาตรงนี้
        print(f"⚠️ AI Process Error: {ai_err}")

    # ✅ STEP 3: ส่งข้อความตอบกลับหาลูกค้า
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=bot_reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
