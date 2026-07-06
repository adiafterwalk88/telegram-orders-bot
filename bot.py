import requests
from flask import Flask, jsonify
import threading
import os

TOKEN = "8606571929:AAFqbhJqyunPuKO4zDlaedNHYO_JGXPfLhQ"
URL = f"https://api.telegram.org/bot{TOKEN}"

orders = []
app = Flask(__name__)

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def create_order(text, chat_id):
    parts = text.split(',')
    if len(parts) >= 3:
        desc = parts[0].strip()
        phone = parts[1].strip()
        price = float(parts[2].strip())
        executor = parts[3].strip() if len(parts) > 3 else "Не указан"
        order = {"id": len(orders) + 1, "desc": desc, "phone": phone, "price": price, "executor": executor, "status": "Новый"}
        orders.append(order)
        send_message(chat_id, f"✅ Заказ №{order['id']}\n📝 {desc}\n📱 {phone}\n💰 {price} Br\n👤 {executor}")
    else:
        send_message(chat_id, "❌ Формат:\nОписание, телефон, сумма, исполнитель")

def list_orders(chat_id):
    if not orders:
        send_message(chat_id, "📋 Нет заказов")
        return
    text = "📋 Заказы:\n\n"
    for o in orders[-10:]:
        text += f"№{o['id']} | {o['desc']} | {o['price']} Br | {o['status']}\n"
    send_message(chat_id, text)

def handle_message(msg):
    chat_id = msg['chat']['id']
    text = msg.get('text', '')
    if text.startswith('/start'):
        send_message(chat_id, "🤖 Бот приёма заказов\n\nОтправьте заказ:\nОписание, телефон, сумма, исполнитель")
    elif text.startswith('/orders'):
        list_orders(chat_id)
    else:
        create_order(text, chat_id)

@app.route('/orders')
def get_orders():
    return jsonify(orders)

@app.route('/')
def home():
    return "OK"

def poll():
    offset = 0
    while True:
        try:
            res = requests.get(f"{URL}/getUpdates", params={"offset": offset, "timeout": 30}).json()
            if res.get('ok'):
                for u in res['result']:
                    offset = u['update_id'] + 1
                    if 'message' in u:
                        handle_message(u['message'])
        except:
            pass

if __name__ == "__main__":
    threading.Thread(target=poll, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))