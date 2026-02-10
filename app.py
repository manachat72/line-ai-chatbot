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

# แก้บั๊ก URL Database
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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
    
    # ✅ แก้ไข: ประกาศตัวแปรไว้ก่อน กันพัง!
    bot_reply = "กำลังประมวลผล..." 

    try:
        # 1. ให้ Gemini คิด
        response = model.generate_content(user_msg)
        if response.text:
            bot_reply = response.text # อัปเดตคำตอบถ้าคิดออก
        else:
            bot_reply = "นึกไม่ออกครับ (No Text)"

        # 2. เก็บลง Database
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
                print(f"Database Error: {db_err}")
                # ไม่ต้องแก้ bot_reply ถ้า Database พัง บอทจะได้ตอบ user ได้ปกติ
            
    except Exception as e:
        # ถ้าพังตรง Gemini ให้บอก Error ไปเลย
        print(f"Main Error: {e}")
        bot_reply = f"ระบบขัดข้อง: {str(e)}"

    # 3. ส่งข้อความกลับ (บรรทัดนี้จะไม่พังแล้ว เพราะ bot_reply มีค่าเสมอ)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=bot_reply)
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
