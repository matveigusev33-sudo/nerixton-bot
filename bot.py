from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from openai import OpenAI
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from datetime import datetime
import urllib.parse
import json
import requests
import os
import pickle

TELEGRAM_TOKEN = "8766389423:AAF9QEqN2bVgp_4MFjha-bUuxbUXJd6hmzs"
OPENROUTER_API_KEY = "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"
WEATHER_API_KEY = "5aaf1f97a329e98a1239f382961c7222"

ADMIN_USERNAME = "nerixton"
ADMIN_ID = 7551939621
FREE_LIMIT = 20
UNLIMITED_GROUP_ID = -1002501229101

DATA_FILE = "nerixton_data.pkl"

client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

now = datetime.now()
SYSTEM_PROMPT = f"""Ты Nerixton AI — персональный ИИ-ассистент. Сегодня {now.strftime("%d.%m.%Y")} год.
ВАЖНЫЕ ПРАВИЛА:
- Ты говоришь ТОЛЬКО на русском языке
- Ты никогда не упоминаешь DeepSeek, OpenAI, ChatGPT
- Ты не говоришь "как языковая модель", "как ИИ" и подобное
- Ты Nerixton AI и отвечаешь как живой человек
- У тебя есть VIP безлимит за 10₽, покупка через @nerixton
- Не используй Markdown, звёздочки, решётки и форматирование"""

conversations = {}
daily_usage = {}
unlimited_users = set()
unlimited_usernames = set()
vip_requests = set()
all_users = set()
all_groups = set()
total_requests_per_user = {}

def save_data():
    try:
        data = {
            "daily_usage": daily_usage,
            "unlimited_users": unlimited_users,
            "unlimited_usernames": unlimited_usernames,
            "vip_requests": vip_requests,
            "all_users": all_users,
            "all_groups": all_groups,
            "total_requests_per_user": total_requests_per_user
        }
        with open(DATA_FILE, "wb") as f:
            pickle.dump(data, f)
    except:
        pass

def load_data():
    global daily_usage, unlimited_users, unlimited_usernames, vip_requests, all_users, all_groups, total_requests_per_user
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "rb") as f:
                data = pickle.load(f)
                daily_usage = data.get("daily_usage", {})
                unlimited_users = data.get("unlimited_users", set())
                unlimited_usernames = data.get("unlimited_usernames", set())
                vip_requests = data.get("vip_requests", set())
                all_users = data.get("all_users", set())
                all_groups = data.get("all_groups", set())
                total_requests_per_user = data.get("total_requests_per_user", {})
    except:
        pass

load_data()

def is_admin(username):
    return username == ADMIN_USERNAME

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 Перезапустить", callback_data="restart")],
        [InlineKeyboardButton("💎 VIP Безлимит — 10₽", callback_data="vip")]
    ]
    return InlineKeyboardMarkup(keyboard)

def clean_text(text):
    return text.replace("**", "").replace("*", "").replace("__", "").replace("`", "").replace("#", "").replace("##", "").replace("###", "")

def is_vip_user(user_id, username):
    if user_id in unlimited_users:
        return True
    if username and username in unlimited_usernames:
        return True
    return False

def check_limit(user_id, chat_id, username=None):
    if is_vip_user(user_id, username):
        return True, "безлимит"
    if chat_id == UNLIMITED_GROUP_ID:
        return True, "безлимит"
    
    now = datetime.now()
    if now.hour < 12:
        period_key = now.strftime("%Y-%m-%d") + "-am"
    else:
        period_key = now.strftime("%Y-%m-%d") + "-pm"
    
    if user_id not in daily_usage or daily_usage[user_id]["period"] != period_key:
        daily_usage[user_id] = {"count": 0, "period": period_key}
    
    if daily_usage[user_id]["count"] >= FREE_LIMIT:
        return False, "Лимит исчерпан"
    
    daily_usage[user_id]["count"] += 1
    if user_id not in total_requests_per_user:
        total_requests_per_user[user_id] = 0
    total_requests_per_user[user_id] += 1
    
    return True, f"Осталось {FREE_LIMIT - daily_usage[user_id]['count']}"

def get_weather(city):
    city_encoded = urllib.parse.quote(city)
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_encoded}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    r = requests.get(url, timeout=10)
    data = r.json()
    if data.get("cod") != 200:
        return None
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    wind = data["wind"]["speed"]
    desc = data["weather"][0]["description"]
    city_name = data["name"]
    return f"🌤 Погода в {city_name}:\n\n🌡 Температура: {temp}°C (ощущается как {feels_like}°C)\n💧 Влажность: {humidity}%\n💨 Ветер: {wind} м/с\n📝 {desc.capitalize()}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    conversations[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if update.effective_chat.type == "private":
        all_users.add(user_id)
        save_data()
        await update.message.reply_text(
            f"👋 Привет! Я Nerixton AI!\n\n🎁 {FREE_LIMIT} запросов/12ч\n💎 VIP безлимит — 10₽\n\nПиши вопрос!",
            reply_markup=get_main_keyboard()
        )
    else:
        all_groups.add(chat_id)
        save_data()
        await update.message.reply_text("Привет! Я Nerixton AI! Пиши 'Нерикс' и вопрос.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "restart":
        chat_id = update.effective_chat.id
        conversations[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
        await query.edit_message_text("🔄 Перезапущено!", reply_markup=get_main_keyboard())
    
    elif query.data == "vip":
        user = update.effective_user
        user_id = user.id
        username = user.username
        
        if is_vip_user(user_id, username):
            await query.edit_message_text("✅ Уже есть VIP!", reply_markup=get_main_keyboard())
            return
        
        uname = f"@{username}" if username else f"id{user_id}"
        vip_requests.add(user_id)
        save_data()
        
        await query.edit_message_text(
            f"💎 VIP Безлимит — 10₽\n\n1. Напиши @nerixton\n2. Отправь 10₽\n3. Сообщи: {uname}",
            reply_markup=get_main_keyboard()
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    user_text = update.message.text
    username = update.effective_user.username

    if chat_type == "private":
        all_users.add(user_id)
        question = user_text
    else:
        all_groups.add(chat_id)
        if not user_text.lower().startswith("нерикс"):
            return
        question = user_text[6:].strip()
        if not question:
            await update.message.reply_text("Напиши вопрос после 'Нерикс'")
            return

    if question.lower().startswith("погода"):
        parts = question.lower().split("погода", 1)
        city = parts[1].strip() if len(parts) > 1 else ""
        if city:
            try:
                w = get_weather(city)
                await update.message.reply_text(w if w else "❌ Город не найден")
                return
            except:
                pass

    can_ask, msg = check_limit(user_id, chat_id, username)
    if not can_ask:
        await update.message.reply_text(f"❌ {msg}", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 VIP за 10₽", callback_data="vip")]
        ]))
        return

    if chat_id not in conversations:
        conversations[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    conversations[chat_id].append({"role": "user", "content": question})
    thinking_msg = await update.message.reply_text("Думаю...")

    for _ in range(2):
        try:
            response = client.chat.completions.create(
                model="deepseek/deepseek-chat",
                messages=conversations[chat_id],
                max_tokens=2000,
                temperature=0.7,
                timeout=30
            )
            reply = clean_text(response.choices[0].message.content)
            conversations[chat_id].append({"role": "assistant", "content": reply})
            await thinking_msg.delete()
            await update.message.reply_text(reply, parse_mode=None)
            save_data()
            return
        except:
            continue
    
    await thinking_msg.delete()
    await update.message.reply_text("⚠️ Ошибка. Попробуй ещё раз.")

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conversations[chat_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await update.message.reply_text("✅ Память очищена!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    is_vip = is_vip_user(user_id, user.username)
    total = total_requests_per_user.get(user_id, 0)
    
    await update.message.reply_text(
        f"👤 {user.first_name}\n💎 VIP: {'✅' if is_vip else '❌'}\n📈 Запросов: {total}"
    )

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.username):
        return
    if not context.args:
        await update.message.reply_text("/adduser @username")
        return
    username = context.args[0].replace("@", "")
    unlimited_usernames.add(username)
    save_data()
    await update.message.reply_text(f"✅ @{username} VIP!")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.username):
        return
    if not context.args:
        return
    username = context.args[0].replace("@", "")
    unlimited_usernames.discard(username)
    save_data()
    await update.message.reply_text(f"✅ @{username} снят VIP")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.username):
        return
    await update.message.reply_text(
        f"📊 Пользователей: {len(all_users)}\n👥 Групп: {len(all_groups)}\n💎 VIP: {len(unlimited_usernames)}"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.username):
        return
    if not context.args:
        return
    text = " ".join(context.args)
    sent = 0
    for uid in all_users:
        try:
            await context.bot.send_message(uid, f"📢 {text}")
            sent += 1
        except:
            pass
    await update.message.reply_text(f"✅ Отправлено: {sent}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print(f"✅ Nerixton AI запущен! VIP: {len(unlimited_usernames)}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
