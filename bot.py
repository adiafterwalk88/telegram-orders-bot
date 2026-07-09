import requests
from flask import Flask, jsonify, request
import os
import re
import json
from bs4 import BeautifulSoup
import time
import threading
from supabase import create_client

TOKEN = "8606571929:AAFqbhJqyunPuKO4zDlaedNHYO_JGXPaLhQ"
URL = f"https://api.telegram.org/bot{TOKEN}"

# ============ ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ============
SUPABASE_URL = "https://ophusgconubcufrzobzyc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9waHVzZ2NvbnViY3Vmcm9ienljIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM1ODc5MjQsImV4cCI6MjA5OTE2MzkyNH0.a1DBm4PkDt1NHHyIDfF_xFqZd7qEhSGwUfdZbnvXKXs"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

ADMIN_IDS = ["8171279171"]
STAFF_IDS = ["8171279171"]
last_message_time = {}

app = Flask(__name__)

# ============ СИСТЕМА СКИДОК ============
LOYALTY_LEVELS = {
    'bronze': {'min_sum': 0, 'discount': 0, 'name': 'Бронза'},
    'silver': {'min_sum': 2000, 'discount': 2, 'name': 'Серебро'},
    'gold': {'min_sum': 4000, 'discount': 4, 'name': 'Золото'},
    'platinum': {'min_sum': 6000, 'discount': 6, 'name': 'Платина'},
    'diamond': {'min_sum': 10000, 'discount': 7, 'name': 'Бриллиант'},
}

RESTRICTED_BRANDS = ['STIHL', 'HUSQVARNA', 'ШТИЛЬ', 'ХУСКВАРНА', 'stihl', 'husqvarna', 'штиль', 'хускварна']
MAX_DISCOUNT_RESTRICTED = 2

RESTRICTED_CATEGORIES = [
    'cep', 'цепь', 'shina', 'шина', 'zvezdochka', 'звездочка', 'svecha', 'свеча',
    'katushka', 'катушка', 'karbyurator', 'карбюратор', 'porshen', 'поршень',
    'cilindr', 'цилиндр', 'starter', 'стартер', 'glushitel', 'глушитель',
    'salnik', 'сальник', 'podshipnik', 'подшипник', 'prokladka', 'прокладка',
    'nozh', 'нож', 'leska', 'леска', 'remen', 'ремень', 'filt', 'фильт',
    'maslo', 'масло', 'zapchast', 'запчаст', 'rashod', 'расход',
]

EQUIPMENT_CATEGORIES = [
    'benzopil', 'бензопил', 'gazonokosil', 'газонокосил', 'motokos', 'мотокос',
    'generator', 'генератор', 'kompressor', 'компрессор', 'svarochn', 'сварочн',
    'motoblok', 'мотоблок', 'kultivator', 'культиватор', 'dvigatel', 'двигатель',
    'motopomp', 'мотопомп', 'vibroplit', 'виброплит', 'snegoubor', 'снегоубор',
]

def get_client(user_id):
    res = supabase.table('clients').select('*').eq('user_id', user_id).execute()
    if res.data:
        return res.data[0]
    return {"user_id": user_id, "name": "", "phone": "", "address": "", "orders_count": 0, "total_sum": 0, "loyalty_level": "bronze"}

def update_client(user_id, data):
    existing = supabase.table('clients').select('*').eq('user_id', user_id).execute()
    if existing.data:
        supabase.table('clients').update(data).eq('user_id', user_id).execute()
    else:
        data['user_id'] = user_id
        supabase.table('clients').insert(data).execute()

def get_loyalty_level(user_id):
    c = get_client(user_id)
    total_sum = c.get('total_sum', 0)
    level = 'bronze'
    for lvl, data in sorted(LOYALTY_LEVELS.items(), key=lambda x: x[1]['min_sum'], reverse=True):
        if total_sum >= data['min_sum']:
            level = lvl
            break
    return level, LOYALTY_LEVELS[level]

def is_restricted(url, desc):
    text = (url + ' ' + desc).lower()
    for eq in EQUIPMENT_CATEGORIES:
        if eq in text: return False
    for brand in RESTRICTED_BRANDS:
        if brand.lower() in text: return True
    for cat in RESTRICTED_CATEGORIES:
        if cat in text: return True
    return False

def calculate_price(original_price, user_id, url='', desc=''):
    level, data = get_loyalty_level(user_id)
    discount = data['discount']
    if is_restricted(url, desc) and discount > MAX_DISCOUNT_RESTRICTED:
        discount = MAX_DISCOUNT_RESTRICTED
    if discount > 0:
        discounted = original_price * (1 - discount / 100)
        return round(discounted, 2), discount, data['name']
    return original_price, 0, data['name']

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def send_to_staff(text):
    for uid in STAFF_IDS:
        try: send_message(uid, text)
        except: pass

def save_order(order_data):
    supabase.table('orders').insert(order_data).execute()

def get_new_orders():
    res = supabase.table('orders').select('*').eq('status', 'Новый').order('id', desc=False).execute()
    return res.data

def mark_imported(order_ids):
    for oid in order_ids:
        supabase.table('orders').update({'status': 'Импортирован'}).eq('id', oid).execute()

def parse_brest_motors(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        result = {'url': url, 'desc': '', 'phone': '', 'price': 0, 'available': 'Проверить'}
        h1 = soup.find('h1', itemprop='name') or soup.find('h1')
        if h1: result['desc'] = h1.get_text(strip=True)
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and 'offers' in data:
                    result['price'] = float(data['offers'].get('price', 0))
                    avail = data['offers'].get('availability', '')
                    if 'InStock' in str(avail): result['available'] = '✅ В наличии'
                    elif 'OutOfStock' in str(avail): result['available'] = '❌ Нет в наличии'
                    break
            except: pass
        if not result['price']:
            text = soup.get_text()
            match = re.search(r'(\d+[\.,\s]*\d*)\s*(?:р|руб|Br|BYN)', text)
            if match: result['price'] = float(match.group(1).replace(' ', '').replace(',', '.'))
        phones = re.findall(r'\+375\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}', resp.text)
        if phones: result['phone'] = phones[0]
        return result
    except:
        return {'url': url, 'desc': 'Ошибка', 'phone': '', 'price': 0}

def handle_message(msg):
    chat_id = str(msg['chat']['id'])
    text = msg.get('text', '')
    user_id = str(msg['from']['id'])
    username = msg.get('from', {}).get('first_name', 'Клиент')
    
    c = get_client(user_id)
    last_message_time[user_id] = time.time()

    if text.startswith('/start'):
        level, data = get_loyalty_level(user_id)
        send_message(chat_id, f"🤖 Бот заказов\n\n👤 ID: <code>{user_id}</code>\n📱 Тел: {c.get('phone','—')}\n🏷️ Уровень: {data['name']} ({data['discount']}%)\n\n🔗 Пришлите ссылку или текст заказа")
    
    elif text.startswith('/profile'):
        level, data = get_loyalty_level(user_id)
        next_level = None
        for lvl, d in sorted(LOYALTY_LEVELS.items(), key=lambda x: x[1]['min_sum']):
            if d['min_sum'] > c.get('total_sum', 0): next_level = (lvl, d); break
        resp = f"👤 Профиль\n\nID: <code>{user_id}</code>\n📱 Тел: {c.get('phone','—')}\n💵 Сумма: {c.get('total_sum',0)} Br\n🏷️ {data['name']} ({data['discount']}%)"
        if next_level: resp += f"\n📈 До {next_level[1]['name']}: {max(0, next_level[1]['min_sum'] - c.get('total_sum',0))} Br"
        send_message(chat_id, resp)
    
    elif text.startswith('/orders'):
        res = supabase.table('orders').select('*').eq('user_id', user_id).order('id', desc=True).limit(5).execute()
        if not res.data:
            send_message(chat_id, "📋 Нет заказов")
        else:
            resp = f"📋 Заказы {username}:\n\n"
            for o in res.data:
                resp += f"№{o['id']} | {o.get('product','')[:50]} | {o.get('price',0)} Br | {o.get('status','Новый')}\n"
            send_message(chat_id, resp)
    
    elif text.startswith('/phone '):
        update_client(user_id, {'phone': text.split('/phone ')[1].strip()})
        send_message(chat_id, "✅ Телефон сохранён")
    
    elif text.startswith('/address '):
        update_client(user_id, {'address': text.split('/address ', 1)[1].strip()})
        send_message(chat_id, "✅ Адрес сохранён")
    
    elif text.startswith('/help'):
        send_message(chat_id, "🤖 Бот заказов\n\n🔗 Пришлите ссылку на brest-motors.by\n📝 Или текст заказа\n\n/orders — мои заказы\n/profile — профиль\n/phone — сохранить телефон\n/address — сохранить адрес")
    
    else:
        urls = re.findall(r'https?://[^\s]+', text)
        client_phone = c.get('phone', '')
        client_address = c.get('address', '')
        
        if not client_phone:
            send_message(chat_id, "📱 Укажите номер телефона.\n/phone +375291234567")
            return
        
        if not client_address:
            send_message(chat_id, "📍 Укажите адрес доставки.\n/address г. Брест, ул. Ленина 5")
            return
        
        if urls: send_message(chat_id, f"🔍 Парсинг {urls[0]}...")
        
        if urls and 'brest-motors.by' in urls[0]:
            data = parse_brest_motors(urls[0])
        else:
            phone_match = re.search(r'(\+?\d{10,15})', text.replace(' ', '').replace('-', ''))
            phone = phone_match.group(1) if phone_match else client_phone
            price_match = re.search(r'(\d+)\s*(?:р|руб|br|BYN|Br)', text, re.IGNORECASE)
            price = float(price_match.group(1)) if price_match else 0
            desc = text
            if phone_match: desc = desc.replace(phone_match.group(0), '')
            if price_match: desc = desc.replace(price_match.group(0), '')
            desc = desc.strip() or 'Без описания'
            data = {'phone': phone, 'desc': desc, 'price': price, 'url': urls[0] if urls else ''}

        original_price = data.get('price', 0)
        final_price, discount_percent, level_name = calculate_price(original_price, user_id, data.get('url', ''), data['desc'])
        
        order = {
            'customer': username,
            'phone': data.get('phone', client_phone),
            'address': client_address,
            'product': data['desc'],
            'price': final_price,
            'prepaid': 0,
            'status': 'Новый',
            'executor': 'Не назначен',
            'user_id': user_id,
            'url': data.get('url', ''),
            'source': 'бот'
        }
        save_order(order)
        
        c['orders_count'] = c.get('orders_count', 0) + 1
        update_client(user_id, {'orders_count': c['orders_count'], 'phone': client_phone})
        
        resp = f"✅ Заказ создан!\n📝 {data['desc'][:200]}\n📱 {client_phone}\n📍 {client_address}\n💰 {final_price} Br"
        if discount_percent > 0: resp += f"\n🎉 Скидка: {discount_percent}% ({level_name})"
        send_message(chat_id, resp)
        send_to_staff(f"🔔 Новый заказ!\n👤 {username}\n📝 {data['desc'][:150]}\n💰 {final_price} Br")

def auto_reply_loop():
    while True:
        time.sleep(300)
        now = time.time()
        for uid, lt in list(last_message_time.items()):
            if now - lt > 3600:
                c = get_client(uid)
                if c.get('orders_count', 0) == 0:
                    try:
                        send_message(uid, "👋 Давно не виделись! Пришлите ссылку на товар.")
                        last_message_time[uid] = now
                    except: pass

threading.Thread(target=auto_reply_loop, daemon=True).start()

# ============ API ============
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if 'message' in data: handle_message(data['message'])
    return jsonify({"ok": True})

@app.route('/orders')
def get_orders():
    return jsonify(get_new_orders())

@app.route('/orders/import', methods=['POST'])
def import_orders():
    ids = request.json.get('ids', [])
    mark_imported(ids)
    return jsonify({"ok": True})

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    requests.post(f"{URL}/setWebhook", json={"url": "https://telegram-orders-bot-7k4f.onrender.com/webhook"})
    print("Бот v8 с Supabase запущен")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
