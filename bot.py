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
        clients[user_id] = {"name": "", "phone": "", "address": "", "orders_count": 0, "completed_orders": 0, "total_sum": 0}
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
        elif soup.find('h1'): result['desc'] = soup.find('h1').get_text(strip=True)
        
        sku = soup.find('span', itemprop='sku')
        if sku: result['sku'] = sku.get_text(strip=True)
        
        brand = soup.find('span', itemprop='name')
        if brand and brand.parent.name == 'a': result['brand'] = brand.get_text(strip=True)
        
        if result['sku']: result['desc'] += f' (Арт: {result["sku"]})'
        if result['brand']: result['desc'] += f' - {result["brand"]}'
        
        price_found = False
        
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if 'offers' in data and isinstance(data['offers'], dict):
                        result['price'] = float(data['offers'].get('price', 0))
                        price_found = True
                        avail = data['offers'].get('availability', '')
                        if 'InStock' in str(avail): result['available'] = '✅ В наличии'
                        elif 'OutOfStock' in str(avail): result['available'] = '❌ Нет в наличии'
                        break
                    if 'price' in data:
                        result['price'] = float(data['price'])
                        price_found = True
                        break
            except: pass
        
        if not price_found:
            for meta in soup.find_all('meta'):
                prop = str(meta.get('property', '') + meta.get('itemprop', ''))
                if 'price' in prop.lower():
                    content = meta.get('content', '')
                    nums = re.findall(r'\d+', str(content).replace(' ', ''))
                    if nums:
                        result['price'] = float(nums[0])
                        price_found = True
                        break
        
        if not price_found:
            price_selectors = [
                {'class': re.compile(r'price|Price|product-price|special-price|autocalc-product-price')},
                {'itemprop': 'price'},
                {'id': re.compile(r'price|Price')},
            ]
            for sel in price_selectors:
                el = soup.find(['span', 'div', 'p', 'strong', 'b'], sel)
                if el:
                    text = el.get_text(strip=True)
                    text_clean = re.sub(r'[^\d.,]', '', text.replace(' ', ''))
                    nums = re.findall(r'\d+', text_clean)
                    if nums:
                        result['price'] = float(nums[0])
                        price_found = True
                        break
        
        if not price_found:
            text = soup.get_text()
            price_patterns = [
                r'цена[:\s]*(\d+[\.,\s]*\d*)',
                r'стоимость[:\s]*(\d+[\.,\s]*\d*)',
                r'(\d+[\.,\s]*\d*)\s*(?:р|руб|Br|BYN|бел\.руб)',
                r'(\d+[\.,\s]*\d*)\s*(?:р\.|руб\.|Br)',
            ]
            for pat in price_patterns:
                match = re.search(pat, text, re.IGNORECASE)
                if match:
                    num_str = match.group(1).replace(' ', '').replace(',', '.')
                    try:
                        result['price'] = float(num_str)
                        price_found = True
                        break
                    except: pass
        
        phones = re.findall(r'\+375\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}', resp.text)
        if phones: result['phone'] = phones[0]
        
        text = soup.get_text().lower()
        if 'в наличии' in text: result['available'] = '✅ В наличии'
        elif 'нет в наличии' in text or 'распродано' in text: result['available'] = '❌ Нет в наличии'
        elif 'под заказ' in text: result['available'] = '📦 Под заказ'
        
        return result
    except Exception as e:
        print(f"Ошибка: {e}")
        return {'url': url, 'desc': 'Ошибка', 'phone': '', 'price': 0}

def handle_message(msg):
    chat_id = str(msg['chat']['id'])
    text = msg.get('text', '')
    user_id = str(msg['from']['id'])
    username = msg.get('from', {}).get('first_name', 'Клиент')
    
    if user_id not in clients:
        clients[user_id] = {"name": username, "phone": "", "address": "", "orders_count": 0, "completed_orders": 0, "total_sum": 0}
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
        send_message(chat_id, f"🤖 Бот заказов brest-motors.by\n\n👤 ID: <code>{user_id}</code>\n📱 Тел: {c.get('phone','—')}\n📍 Адрес: {c.get('address','—')}\n🏷️ Уровень: {data['name']} ({data['discount']}%)\n📊 Заказов: {c.get('orders_count',0)}\n\n🔗 Пришлите ссылку или текст заказа")

    elif text.startswith('/profile'):
        c = clients[user_id]
        level, data = get_loyalty_level(user_id)
        next_level = None
        for lvl, d in sorted(LOYALTY_LEVELS.items(), key=lambda x: x[1]['min_sum']):
            if d['min_sum'] > c.get('total_sum', 0):
                next_level = (lvl, d)
                break
        resp = f"👤 <b>Профиль</b>\n\nID: <code>{user_id}</code>\nИмя: {c['name']}\n📱 Тел: {c.get('phone','—')}\n📍 Адрес: {c.get('address','—')}\n📊 Заказов: {c.get('orders_count',0)}\n✅ Выполнено: {c.get('completed_orders',0)}\n💵 Сумма: {c.get('total_sum',0)} Br\n🏷️ Уровень: {data['name']} ({data['discount']}%)\n"
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

    elif text.startswith('/address '):
        addr = text.split('/address ', 1)[1].strip()
        clients[user_id]['address'] = addr
        send_message(chat_id, f"✅ Адрес сохранён: {addr}")
    elif text.startswith('/help'):
        resp = "🤖 <b>Бот заказов brest-motors.by</b>\n\n"
        resp += "<b>📋 Основные команды:</b>\n"
        resp += "/start — регистрация и приветствие\n"
        resp += "/profile — мой профиль и скидка\n"
        resp += "/orders — мои заказы (последние 5)\n\n"
        resp += "<b>📱 Контакты:</b>\n"
        resp += "/phone +375291234567 — сохранить телефон\n"
        resp += "/address г. Брест, ул. Ленина 5 — сохранить адрес\n\n"
        resp += "<b>🛒 Как заказать:</b>\n"
        resp += "1. Пришлите ссылку на товар с brest-motors.by\n"
        resp += "2. Или напишите: описание, цена\n"
        resp += "3. Бот сам найдет цену, артикул и наличие\n\n"
        resp += "<b>💰 Скидки:</b>\n"
        resp += "• Бронза — 0%\n"
        resp += "• Серебро (2000+ Br) — 2%\n"
        resp += "• Золото (4000+ Br) — 4%\n"
        resp += "• Платина (6000+ Br) — 6%\n"
        resp += "• Бриллиант (10000+ Br) — 7%\n"
        resp += "На запчасти Stihl/Husqvarna — макс. 2%\n\n"
        resp += "<b>📞 Связь:</b>\n"
        resp += "По вопросам: +375 29 818 18 04\n"
        resp += "Email: Kvalimbel@mail.ru"
        send_message(chat_id, resp)
    else:
        urls = re.findall(r'https?://[^\s]+', text)
        client_phone = clients[user_id].get('phone', '')
        client_address = clients[user_id].get('address', '')
        
        # Шаг 1: Нет телефона
        if not client_phone:
            if urls:
                clients[user_id]['pending_url'] = urls[0]
                clients[user_id]['pending_text'] = text
                send_message(chat_id, "📱 Для оформления заказа укажите ваш номер телефона.\n\nФормат: +375 29 123 45 67")
            else:
                phone_match = re.search(r'(\+?\d{10,15})', text.replace(' ', '').replace('-', ''))
                if phone_match:
                    clients[user_id]['phone'] = phone_match.group(1)
                    send_message(chat_id, f"✅ Телефон сохранён!\n\n📍 Теперь укажите ваш адрес доставки.")
                else:
                    send_message(chat_id, "📱 Укажите ваш номер телефона.\n\nФормат: +375 29 123 45 67")
            return
        
        # Шаг 2: Нет адреса
        if not client_address:
            if urls:
                clients[user_id]['pending_url'] = urls[0]
                clients[user_id]['pending_text'] = text
                send_message(chat_id, "📍 Укажите ваш адрес доставки.\n\nФормат: г. Брест, ул. Ленина, д. 1")
            else:
                phone_match = re.search(r'^(\+?\d{10,15})$', text.replace(' ', '').replace('-', ''))
                if phone_match:
                    clients[user_id]['phone'] = phone_match.group(1)
                    send_message(chat_id, f"✅ Телефон обновлён!\n\n📍 Теперь укажите ваш адрес доставки.")
                else:
                    clients[user_id]['address'] = text.strip()
                    send_message(chat_id, f"✅ Адрес сохранён: {text.strip()}\n\nТеперь пришлите ссылку на товар или описание заказа.")
            return
        
        # Шаг 3: Создание заказа
        pending_url = clients[user_id].get('pending_url', '')
        pending_text = clients[user_id].get('pending_text', '')
        if pending_url:
            urls = [pending_url]
            text = pending_text
            clients[user_id].pop('pending_url', None)
            clients[user_id].pop('pending_text', None)
        
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
            data = {'phone': phone, 'desc': desc, 'price': price, 'url': urls[0] if urls else '', 'address': client_address}

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
        if not data.get('address'): data['address'] = client_address
        orders.append(data)
        clients[user_id]['orders_count'] = clients[user_id].get('orders_count', 0) + 1

        resp = f"✅ <b>Заказ №{data['id']}!</b>\n👤 {username}\n🏷️ {level_name}\n📝 {data['desc'][:200]}\n📱 {data['phone']}\n📍 {data.get('address','—')}\n"
        if discount_percent > 0:
            resp += f"💰 Базовая: {original_price} Br\n🎉 Скидка: {discount_percent}%\n💎 Итог: <b>{final_price} Br</b>\n"
        else:
            resp += f"💰 {final_price} Br\n"
        if data.get('available'): resp += f"{data['available']}\n"
        if data.get('url'): resp += f"🔗 {data['url']}"
        send_message(chat_id, resp)

        staff_msg = f"🔔 Новый заказ №{data['id']}!\n👤 {username} ({level_name})\n📝 {data['desc'][:150]}\n📱 {data['phone']}\n📍 {data.get('address','—')}\n"
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
    print("Бот v6 запущен")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
