import requests
from flask import Flask, jsonify, request
import os
import re
import json
from bs4 import BeautifulSoup
import time
import threading

TOKEN = "8606571929:AAFqbhJqyunPuKO4zDlaedNHYO_JGXPaLhQ"
URL = f"https://api.telegram.org/bot{TOKEN}"

orders = []
clients = {}
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
    'cep', 'цепь', 'shina', 'шина', 'zvezdochka', 'звездочка', 'maslyanyj nasos', 'масляный насос',
    'vozdushnyj filtr', 'воздушный фильтр', 'toplivnyj filtr', 'топливный фильтр', 'svecha', 'свеча',
    'katushka zazhiganiya', 'катушка зажигания', 'karbyurator', 'карбюратор', 'porshen', 'поршень',
    'cilindr', 'цилиндр', 'kolca', 'кольца', 'kolenval', 'коленвал', 'shatun', 'шатун',
    'starter', 'стартер', 'pruzhina', 'пружина', 'shnur', 'шнур', 'sceplenie', 'сцепление',
    'tormoz cepi', 'тормоз цепи', 'glushitel', 'глушитель', 'shlang', 'шланг', 'bak', 'бак',
    'antivibracionnaya', 'антивибрационная', 'rukoyatka', 'рукоятка', 'kozhuh', 'кожух',
    'natyazhitel', 'натяжитель', 'gajka', 'гайка', 'salnik', 'сальник', 'podshipnik', 'подшипник',
    'prokladka', 'прокладка', 'iskrogasitel', 'искрогаситель',
    'praimer', 'праймер', 'val', 'вал', 'shtanga', 'штанга', 'reduktor', 'редуктор',
    'golovka', 'головка', 'nozh', 'нож', 'katushka s leskoj', 'катушка с леской',
    'leska', 'леска', 'remen', 'ремень',
    'maslyanyj filtr', 'масляный фильтр', 'klapan', 'клапан', 'maslosemnyj', 'маслосъемный',
    'raspredval', 'распредвал', 'tolkatel', 'толкатель', 'koromyslo', 'коромысло',
    'shchup', 'щуп', 'grm', 'грм',
    'bolt', 'болт', 'adapter', 'адаптер', 'koleso', 'колесо', 'kryshka deki', 'крышка деки',
    'travosbornik', 'травосборник', 'tros', 'трос', 'privod', 'привод', 'transmissiya', 'трансмиссия',
    'zapchast', 'запчаст', 'rashod', 'расход', 'maslo', 'масло', 'smazka', 'смазка',
    'filt', 'фильт', 'remkomplekt', 'ремкомплект', 'kryshka', 'крышка', 'probka', 'пробка',
]

EQUIPMENT_CATEGORIES = [
    'benzopil', 'бензопил', 'elektropil', 'электропил', 'pila', 'пила',
    'gazonokosil', 'газонокосил', 'motokos', 'мотокос', 'trimmer', 'триммер',
    'generator', 'генератор', 'kompressor', 'компрессор', 'svarochn', 'сварочн',
    'motoblok', 'мотоблок', 'трактор', 'traktor', 'kultivator', 'культиватор',
    'dvigatel', 'двигатель', 'motopomp', 'мотопомп', 'vibroplit', 'виброплит',
    'snegoubor', 'снегоубор', 'lodochn', 'лодочн', 'minitraktor', 'rajder', 'райдер',
]

def get_loyalty_level(user_id):
    c = clients.get(user_id, {})
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
        if eq in text:
            return False
    for brand in RESTRICTED_BRANDS:
        if brand.lower() in text:
            return True
    for cat in RESTRICTED_CATEGORIES:
        if cat in text:
            return True
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

def update_client_stats(user_id, price, completed=False):
    if user_id not in clients:
        clients[user_id] = {"name": "", "phone": "", "orders_count": 0, "completed_orders": 0, "total_sum": 0}
    c = clients[user_id]
    if completed:
        c['completed_orders'] = c.get('completed_orders', 0) + 1
        c['total_sum'] = c.get('total_sum', 0) + price

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def send_to_staff(text):
    for uid in STAFF_IDS:
        try:
            send_message(uid, text)
        except:
            pass

def parse_brest_motors(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        result = {'url': url, 'desc': '', 'phone': '', 'price': 0, 'sku': '', 'brand': '', 'available': 'Проверить'}
        h1 = soup.find('h1', itemprop='name')
        if h1: result['desc'] = h1.get_text(strip=True)
        sku = soup.find('span', itemprop='sku')
        if sku: result['sku'] = sku.get_text(strip=True)
        brand = soup.find('span', itemprop='name')
        if brand and brand.parent.name == 'a': result['brand'] = brand.get_text(strip=True)
        if result['sku']: result['desc'] += f' (Арт: {result["sku"]})'
        if result['brand']: result['desc'] += f' - {result["brand"]}'
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if 'offers' in data:
                    result['price'] = float(data['offers'].get('price', 0))
                    avail = data['offers'].get('availability', '')
                    if 'InStock' in avail: result['available'] = '✅ В наличии'
                    elif 'OutOfStock' in avail: result['available'] = '❌ Нет в наличии'
                    elif 'PreOrder' in avail: result['available'] = '📦 Под заказ'
                    break
            except: pass
        if not result['price']:
            price_el = soup.find('span', class_=re.compile(r'price|Price|autocalc'))
            if price_el:
                nums = re.findall(r'\d+', price_el.get_text().replace(' ', ''))
                if nums: result['price'] = float(nums[0])
        text = soup.get_text()
        if 'в наличии' in text.lower(): result['available'] = '✅ В наличии'
        elif 'нет в наличии' in text.lower(): result['available'] = '❌ Нет в наличии'
        elif 'под заказ' in text.lower(): result['available'] = '📦 Под заказ'
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
    
    if user_id not in clients:
        clients[user_id] = {"name": username, "phone": "", "orders_count": 0, "completed_orders": 0, "total_sum": 0}
    last_message_time[user_id] = time.time()

    # Админ-панель
    if text.startswith('/admin') and user_id in ADMIN_IDS:
        total = len(orders)
        active = len([o for o in orders if o.get('status') != 'Выполнен'])
        resp = f"📊 <b>Админ-панель</b>\n\n📦 Всего: {total}\n🔄 Активных: {active}\n👥 Клиентов: {len(clients)}\n\n<b>Последние 5:</b>\n"
        for o in orders[-5:]:
            resp += f"№{o['id']} | {o['desc'][:40]} | {o['price']} Br | {o.get('status','Новый')}\n"
        send_message(chat_id, resp)

    elif text.startswith('/all') and user_id in ADMIN_IDS:
        resp = "📋 <b>Все заказы:</b>\n\n"
        for o in orders:
            resp += f"№{o['id']} | {o['desc'][:50]} | {o['price']} Br | {o.get('status','Новый')}\n"
        send_message(chat_id, resp[:4000])

    elif text.startswith('/done ') and user_id in ADMIN_IDS:
        try:
            oid = int(text.split()[1])
            order = next((o for o in orders if o['id'] == oid), None)
            if order:
                order['status'] = 'Выполнен'
                uid = order.get('user_id', '')
                if uid:
                    update_client_stats(uid, order.get('final_price', order.get('price', 0)), completed=True)
                send_message(chat_id, f"✅ Заказ №{oid} выполнен!")
                if uid:
                    send_message(uid, f"🎉 Ваш заказ №{oid} выполнен!")
            else:
                send_message(chat_id, "❌ Не найден")
        except:
            send_message(chat_id, "❌ /done НОМЕР")

    # Клиентские команды
    elif text.startswith('/start'):
        c = clients[user_id]
        level, data = get_loyalty_level(user_id)
        send_message(chat_id, f"🤖 Бот заказов brest-motors.by\n\n👤 ID: <code>{user_id}</code>\n📱 Тел: {c.get('phone','—')}\n🏷️ Уровень: {data['name']} ({data['discount']}%)\n📊 Заказов: {c.get('orders_count',0)}\n\n🔗 Пришлите ссылку или текст заказа")

    elif text.startswith('/profile'):
        c = clients[user_id]
        level, data = get_loyalty_level(user_id)
        next_level = None
        for lvl, d in sorted(LOYALTY_LEVELS.items(), key=lambda x: x[1]['min_sum']):
            if d['min_sum'] > c.get('total_sum', 0):
                next_level = (lvl, d)
                break
        resp = f"👤 <b>Профиль</b>\n\nID: <code>{user_id}</code>\nИмя: {c['name']}\nТел: {c.get('phone','—')}\n📊 Заказов: {c.get('orders_count',0)}\n✅ Выполнено: {c.get('completed_orders',0)}\n💵 Сумма: {c.get('total_sum',0)} Br\n🏷️ Уровень: {data['name']} ({data['discount']}%)\n"
        if next_level:
            need = next_level[1]['min_sum'] - c.get('total_sum', 0)
            resp += f"\n📈 До {next_level[1]['name']}: {max(0,need)} Br"
        send_message(chat_id, resp)

    elif text.startswith('/orders'):
        user_orders = [o for o in orders if o.get('user_id') == user_id]
        if not user_orders:
            send_message(chat_id, "📋 Нет заказов")
        else:
            resp = f"📋 <b>Заказы {username}:</b>\n\n"
            for o in user_orders[-5:]:
                resp += f"№{o['id']} | {o['desc'][:50]} | {o.get('final_price',o.get('price',0))} Br | {o.get('status','Новый')}\n"
            send_message(chat_id, resp)

    elif text.startswith('/phone '):
        clients[user_id]['phone'] = text.split('/phone ')[1].strip()
        send_message(chat_id, "✅ Телефон сохранён")

    else:
        urls = re.findall(r'https?://[^\s]+', text)
        if urls: send_message(chat_id, f"🔍 Парсинг {urls[0]}...")
        
        if urls and 'brest-motors.by' in urls[0]:
            data = parse_brest_motors(urls[0])
        else:
            phone_match = re.search(r'(\+?\d{10,15})', text.replace(' ', '').replace('-', ''))
            phone = phone_match.group(1) if phone_match else clients[user_id].get('phone', 'Не указан')
            price_match = re.search(r'(\d+)\s*(?:р|руб|br|BYN|Br)', text, re.IGNORECASE)
            price = float(price_match.group(1)) if price_match else 0
            desc = text
            if phone_match: desc = desc.replace(phone_match.group(0), '')
            if price_match: desc = desc.replace(price_match.group(0), '')
            desc = desc.strip() or 'Без описания'
            data = {'phone': phone, 'desc': desc, 'price': price, 'url': urls[0] if urls else ''}

        original_price = data.get('price', 0)
        final_price, discount_percent, level_name = calculate_price(original_price, user_id, data.get('url', ''), data['desc'])
        
        data['id'] = len(orders) + 1
        data['status'] = 'Новый'
        data['executor'] = 'Не назначен'
        data['user_id'] = user_id
        data['customer'] = username
        data['date'] = time.strftime('%d.%m.%Y')
        data['original_price'] = original_price
        data['final_price'] = final_price
        data['discount'] = discount_percent
        data['loyalty_level'] = level_name
        orders.append(data)
        clients[user_id]['orders_count'] = clients[user_id].get('orders_count', 0) + 1
        if data.get('phone') != 'Не указан': clients[user_id]['phone'] = data.get('phone', '')

        resp = f"✅ <b>Заказ №{data['id']}!</b>\n👤 {username}\n🏷️ {level_name}\n📝 {data['desc'][:200]}\n📱 {data['phone']}\n"
        if discount_percent > 0:
            resp += f"💰 Базовая: {original_price} Br\n🎉 Скидка: {discount_percent}%\n💎 Итог: <b>{final_price} Br</b>\n"
        else:
            resp += f"💰 {final_price} Br\n"
        if data.get('available'): resp += f"{data['available']}\n"
        if data.get('url'): resp += f"🔗 {data['url']}"
        send_message(chat_id, resp)

        staff_msg = f"🔔 Новый заказ №{data['id']}!\n👤 {username} ({level_name})\n📝 {data['desc'][:150]}\n📱 {data['phone']}\n"
        if discount_percent > 0:
            staff_msg += f"💰 База: {original_price} Br | -{discount_percent}% | Итог: {final_price} Br\n"
        else:
            staff_msg += f"💰 {final_price} Br\n"
        if data.get('url'): staff_msg += f"🔗 {data['url']}"
        send_to_staff(staff_msg)

def auto_reply_loop():
    while True:
        time.sleep(300)
        now = time.time()
        for uid, lt in list(last_message_time.items()):
            if now - lt > 3600 and clients.get(uid, {}).get('orders_count', 0) == 0:
                try:
                    send_message(uid, "👋 Давно не виделись! Пришлите ссылку на товар с brest-motors.by")
                    last_message_time[uid] = now
                except: pass

threading.Thread(target=auto_reply_loop, daemon=True).start()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if 'message' in data: handle_message(data['message'])
    return jsonify({"ok": True})

@app.route('/orders')
def get_orders(): return jsonify(orders)

@app.route('/clients')
def get_clients(): return jsonify(clients)

@app.route('/clear')
def clear_orders():
    global orders; orders = []; return jsonify({"ok": True})

@app.route('/')
def home(): return "OK"

if __name__ == "__main__":
    requests.post(f"{URL}/setWebhook", json={"url": "https://telegram-orders-bot-7k4f.onrender.com/webhook"})
    print("Бот v5 запущен: скидки, категории, админ-панель")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
