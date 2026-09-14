from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
import pymysql

app = Flask(__name__)
CORS(app)

# Cấu hình kết nối MySQL
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '123456',
    'database': 'gemini_chat_db',
    'cursorclass': pymysql.cursors.DictCursor
}

# Khởi tạo Gemini Client
client = genai.Client(api_key="AQ.Ab8RN6JQavRsndMLM_XFsUL2G_I_Dw8MJiAHvxIxHKEktEB_rA")

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    data = request.json
    user_message = data.get("message")
    conversation_id = data.get("conversation_id") # Nhận ID phiên chat nếu có từ Frontend

    if not user_message:
        return jsonify({"error": "Vui lòng nhập tin nhắn"}), 400

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # 1. Nếu chưa có conversation_id, tạo mới phiên chat trong DB
            if not conversation_id:
                cursor.execute(
                    "INSERT INTO conversations (user_id, title) VALUES (%s, %s)",
                    (1, user_message[:30])
                )
                connection.commit()
                conversation_id = cursor.lastrowid

            # 2. Lưu tin nhắn của User vào database
            cursor.execute(
                "INSERT INTO messages (conversation_id, sender_type, content) VALUES (%s, %s, %s)",
                (conversation_id, 'user', user_message)
            )
            connection.commit()

            # 3. Kéo toàn bộ lịch sử tin nhắn cũ của conversation_id này lên
            cursor.execute(
                "SELECT sender_type, content FROM messages WHERE conversation_id = %s ORDER BY created_at ASC",
                (conversation_id,)
            )
            db_messages = cursor.fetchall()

        # Chuyển đổi định dạng tin nhắn thành cấu trúc history chuẩn của google-genai SDK
        history = []
        # Lấy tất cả tin nhắn trừ tin nhắn mới nhất vừa gửi (vì sẽ truyền trực tiếp qua send_message)
        for msg in db_messages[:-1]:
            role = "user" if msg['sender_type'] == 'user' else "model"
            history.append({
                "role": role,
                "parts": [{"text": msg['content']}]
            })

        # 4. Khởi tạo phiên chat kèm System Instruction và Lịch sử cũ
        chat = client.chats.create(
            model="gemini-3.6-flash",
            history=history,
            config=types.GenerateContentConfig(
                system_instruction="Bạn là trợ lý ảo thông minh chuyên trách Hệ thống Quản lý Học tập (LMS). Hãy luôn trả lời ngắn gọn, rõ ràng, hỗ trợ học viên tra cứu tài liệu, lịch học và giải đáp thắc mắc chuyên môn.",
            )
        )

        # 5. Gửi tin nhắn mới vào phiên chat có nhớ ngữ cảnh
        response = chat.send_message(user_message)
        model_reply = response.text

        # 6. Lưu câu trả lời của AI vào database
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO messages (conversation_id, sender_type, content) VALUES (%s, %s, %s)",
                (conversation_id, 'model', model_reply)
            )
            connection.commit()

        return jsonify({
            "status": "success",
            "conversation_id": conversation_id,
            "reply": model_reply
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        connection.close()

if __name__ == '__main__':
    print("🚀 Server Backend & MySQL Chat History đang chạy tại http://127.0.0.1:5000")
    app.run(debug=True, port=5000)