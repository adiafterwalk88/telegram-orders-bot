import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db, add_tracked, get_all_tracked, update_last_price
from parser import fetch_ozon_price

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]

logging.basicConfig(level=logging.INFO)

# Состояния диалога
ARTICLE, TARGET = range(2)

KEYBOARD = ReplyKeyboardMarkup([["/start", "/list"]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправьте артикул товара Ozon (только цифры).\n"
        "Я буду проверять цену и сообщу, если она упадёт.",
        reply_markup=KEYBOARD
    )
    return ARTICLE

async def get_article(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Артикул должен содержать только цифры. Попробуйте ещё раз.")
        return ARTICLE
    context.user_data["article"] = text
    await update.message.reply_text(
        "Укажите целевую цену в рублях (просто число). "
        "Если не хотите задавать порог, отправьте 0 — буду уведомлять о любом снижении."
    )
    return TARGET

async def get_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        target = float(text)
    except ValueError:
        await update.message.reply_text("Введите число, например 1500 или 0.")
        return TARGET

    user_id = update.effective_user.id
    article = context.user_data["article"]
    add_tracked(user_id, article, target if target > 0 else None)

    await update.message.reply_text(
        f"✅ Товар {article} добавлен в отслеживание.\n"
        f"Целевая цена: {'любое снижение' if target == 0 else f'{target} ₽'}\n"
        f"Проверка выполняется раз в день.",
        reply_markup=KEYBOARD
    )
    return ConversationHandler.END

async def list_tracked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = [r for r in get_all_tracked() if r[1] == user_id]
    if not rows:
        await update.message.reply_text("У вас пока нет отслеживаемых товаров.")
        return
    lines = []
    for _, _, article, target, last in rows:
        target_str = f"{target} ₽" if target else "любое снижение"
        last_str = f"{last} ₽" if last else "—"
        lines.append(f"• {article}: цель {target_str}, последняя {last_str}")
    await update.message.reply_text("\n".join(lines))

async def check_prices(context: ContextTypes.DEFAULT_TYPE):
    """Периодическая проверка всех товаров."""
    rows = get_all_tracked()
    for record_id, user_id, article, target, last_price in rows:
        price = await fetch_ozon_price(article)
        if price is None:
            continue
        if last_price is None:
            update_last_price(record_id, price)
            continue
        if price < last_price:
            should_notify = target is None or price <= target
            if should_notify:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🔔 Цена на товар {article} снизилась!\n"
                             f"Было: {last_price} ₽\nСейчас: {price} ₽"
                    )
                except Exception as e:
                    print(f"Ошибка отправки {user_id}: {e}")
        update_last_price(record_id, price)

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ARTICLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_article)],
            TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_target)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    application.add_handler(conv)
    application.add_handler(CommandHandler("list", list_tracked))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_prices, "interval", hours=24, args=[application])
    scheduler.start()

    application.run_polling()

if __name__ == "__main__":
    main()
