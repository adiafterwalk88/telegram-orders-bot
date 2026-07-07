import requests
from flask import Flask, jsonify, request
import os
import re
from bs4 import BeautifulSoup

TOKEN = "8606571929:AAFqbhJqyunPuKO4zDlaedNHYO_JGXPaLhQ"
URL = f"https://api.telegram.org/bot{TOKEN}"

orders = []
app = Flask(__name__)

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def extract_urls(text):
    """Извлекает все ссылки из текста"""
    return re.findall(r'https?://[^\s]+', text)

def parse_url(url):
    """Парсит страницу и пытается извлечь данные заказа"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Убираем скрипты и стили
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        text = soup.get_text(separator=' ', strip=True)
        
        result = {}
        
        # Ищем телефон
        phone_patterns = [
            r'(\+?\d{10,13})',
            r'тел[.:\s]*(\+?\d{10,13})',
            r'телефон[.:\s]*(\+?\d{10,13})',
            r'контакт[.:\s]*(\+?\d{10,13})',
        ]
        for pat in phone_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                result['phone'] = match.group(1).strip()
                break
        
        # Ищем цену
        price_patterns = [
            r'(\d+)\s*(?:р|руб|br|BYN|бел\.?руб|₽|Br)',
            r'цена[.:\s]*(\d+)',
            r'стоимость[.:\s]*(\d+)',
            r'(\d+)\s*(?:рублей|рубля)',
        ]
        for pat in price_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                result['price'] = float(match.group(1))
                break
        
        # Берём заголовок как описание
        title = soup.title.string if soup.title else ''
        h1 = soup.find('h1')
        result['desc'] = (h1.get_text(strip=True) if h1 else title) or 'Заказ с сайта'
        
        return result
    except Exception as e:
        print(f"Ошибка парсинга {url}: {e}")
        return {}

def extract_order(text, username):
    """Извлекает заказ из текста или ссылки"""
    # Проверяем есть ли ссылка
    urls = extract_urls(text)
    
    if urls:
        # Парсим первую ссылку
        data = parse_url(urls[0])
        
        # Убираем ссылку из текста для доп. инфы
        remaining = text
        for u in urls:
            remaining = remaining.replace(u, '').strip()
        
        phone = data.get('phone', '')
        price = data.get('price', 0)
        desc = data.get('desc', 'Заказ с сайта')
        
        # Если есть доп. текст — добавляем к описанию
        if remaining:
            desc = f"{desc}\nПримечание: {remaining}"
    else:
        # Старый парсинг из текста
        phone_match = re.search(r'(\+?\d{10,13})', text.replace(' ', '').replace('-', ''))
        phone = phone_match.group(1) if phone_match else 'Не указан'
        
        price_match = re.search(r'(\d+)\s*(?:р|руб|br|BYN|бел\.?руб)', text, re.IGNORECASE)
        price = float(price_match.group(1)) if price_match else 0
        
        desc = text
        if phone_match: desc = desc.replace(phone_match.group(0), '')
        if price_match: desc = desc.replace(price_match.group(0), '')
        desc = desc.strip().strip(',').strip() or 'Без описания'
    
    return {"phone": phone or 'Не указан', "desc": desc, "price": price, "customer": username, "url": urls[0] if urls else ''}

def handle_message(msg):
    chat_id = msg['chat']['id']
    text = msg.get('text', '')
    username = msg.get('from', {}).get('first_name', 'Клиент')

    if text.startswith('/start'):
        send_message(chat_id, "🤖 <b>Бот приёма заказов</b>\n\n"
                              "📝 <b>Создать заказ текстом:</b>\n"
                              "Ремонт дисплея, 80291234567, 150\n\n"
                              "🔗 <b>Создать заказ по ссылке:</b>\n"
                              "Просто пришлите ссылку на товар/услугу\n\n"
                              "<b>Команды:</b>\n"
                              "/orders — мои заказы\n"
                              "/status — статус заказа")
    elif text.startswith('/orders'):
        user_orders = [o for o in orders if o.get('customer') == username]
        if not user_orders:
            send_message(chat_id, "📋 У вас пока нет заказов")
        else:
            resp = "<b>📋 Ваши заказы:</b>\n\n"
            for o in user_orders[-5:]:
                resp += f"№{o['id']} | {o['desc'][:50]}\n📱 {o['phone']} | 💰 {o['price']} Br\n"
                if o.get('url'): resp += f"🔗 {o['url']}\n"
                resp += "\n"
            send_message(chat_id, resp)
    elif text.startswith('/status '):
        try:
            oid = int(text.split()[1])
            order = next((o for o in orders if o['id'] == oid), None)
            if order:
                msg_text = f"📦 <b>Заказ №{oid}</b>\n📝 {order['desc']}\n📱 {order['phone']}\n💰 {order['price']} Br\n📊 {order.get('status', 'Новый')}"
                if order.get('url'): msg_text += f"\n🔗 {order['url']}"
                send_message(chat_id, msg_text)
            else:
                send_message(chat_id, "❌ Заказ не найден")
        except:
            send_message(chat_id, "❌ Формат: /status НОМЕР")
    else:
        urls = extract_urls(text)
        if urls:
            send_message(chat_id, f"🔍 <b>Обрабатываю ссылку...</b>\n{urls[0]}")
        
        order_data = extract_order(text, username)
        order_data['id'] = len(orders) + 1
        order_data['status'] = 'Новый'
        order_data['executor'] = 'Не назначен'
        orders.append(order_data)
        
        response = f"✅ <b>Заказ №{order_data['id']} создан!</b>\n📝 {order_data['desc'][:100]}\n📱 {order_data['phone']}\n💰 {order_data['price']} Br"
        if order_data.get('url'):
            response += f"\n🔗 Источник: {order_data['url']}"
        
        send_message(chat_id, response)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if 'message' in data:
        handle_message(data['message'])
    return jsonify({"ok": True})

@app.route('/orders')
def get_orders():
    return jsonify(orders)

@app.route('/clear')
def clear_orders():
    global orders
    orders = []
    return jsonify({"ok": True})

@app.route('/')
def home():
    return "OK"

if __name__ == "__main__":
    webhook_url = "https://telegram-orders-bot-7k4f.onrender.com/webhook"
    requests.post(f"{URL}/setWebhook", json={"url": webhook_url})
    print("Бот с парсером ссылок запущен")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
