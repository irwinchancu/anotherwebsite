# bot.py – Enhanced with /check route feature for Koyeb (Dec 2025)
import os
import logging
import sqlite3
import random
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# -------- Tiny web server to keep Koyeb health checks happy --------
from threading import Thread
import uvicorn
from fastapi import FastAPI

app_web = FastAPI()

@app_web.get("/")
async def root():
    return {"status": "alive"}

def run_web_server():
    uvicorn.run(app_web, host="0.0.0.0", port=8000, log_level="error")

# -------------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")  # Required for /check
TIMEZONE = ZoneInfo("Asia/Hong_Kong")
DB_PATH = "bot_data.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QUOTES = [
    "The best time to plant a tree was 20 years ago. The second best time is now.",
    "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    "Believe you can and you're halfway there.",
    "Don't watch the clock; do what it does. Keep going.",
    "Everything you've ever wanted is on the other side of fear.",
]

# Google Maps integration for route checking
try:
    import google.maps
    gmaps = google.maps.Client(key=GOOGLE_MAPS_API_KEY)
except ImportError:
    gmaps = None
except Exception:
    gmaps = None  # Fallback if key is invalid

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS thoughts (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 chat_id INTEGER, timestamp TEXT, text TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS reminders (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 chat_id INTEGER, time_str TEXT, message TEXT)""")
    conn.commit()
    conn.close()

def save_thought(chat_id: int, text: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ts = datetime.now(TIMEZONE).isoformat()
    c.execute("INSERT INTO thoughts (chat_id, timestamp, text) VALUES (?, ?, ?)",
              (chat_id, ts, text.strip()))
    conn.commit()
    conn.close()

def get_thoughts(chat_id: int, today_only: bool = False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if today_only:
        date = datetime.now(TIMEZONE).date().isoformat()
        c.execute("SELECT timestamp, text FROM thoughts WHERE chat_id = ? AND DATE(timestamp) = ? ORDER BY timestamp", (chat_id, date))
    else:
        c.execute("SELECT timestamp, text FROM thoughts WHERE chat_id = ? ORDER BY timestamp DESC LIMIT 30", (chat_id,))
    rows = [{"time": r[0], "text": r[1]} for r in c.fetchall()]
    conn.close()
    return rows

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Your personal reminder + journal bot is active.\n\n"
        "Commands:\n"
        "/remind 08:30 Your message\n"
        "/thought Your thought here\n"
        "/today • /allthoughts • /motivate\n"
        "/check → Fastest driving route home from company"
    )

async def check_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not gmaps:
        await update.message.reply_text(
            "Route check unavailable: Google Maps API key required.\n"
            "Set GOOGLE_MAPS_API_KEY in environment variables."
        )
        return

    origin = "博愛醫院歷屆總理聯誼會梁省德中學, Tsuen Wan, Hong Kong"
    destination = "利東邨東業樓, Ap Lei Chau, Hong Kong"

    try:
        directions = gmaps.directions(
            origin=origin,
            destination=destination,
            mode="driving",
            traffic_model="best_guess",  # Accounts for typical traffic
            departure_time="now"
        )
        if not directions:
            await update.message.reply_text("Unable to retrieve route. Please try again.")
            return

        route = directions[0]
        distance = route['legs'][0]['distance']['text']
        duration = route['legs'][0]['duration_in_traffic']['text'] if 'duration_in_traffic' in route['legs'][0] else route['legs'][0]['duration']['text']
        steps = route['legs'][0]['steps']

        # Summarize key steps (first 7 for brevity)
        step_summary = "Route Steps:\n"
        for i, step in enumerate(steps[:7], 1):
            step_summary += f"{i}. {step['html_instructions'].replace('<b>', '').replace('</b>', '').strip()}\n"
        if len(steps) > 7:
            step_summary += f"... (Total: {len(steps)} steps)"

        response = (
            f"Fastest Driving Route (Company → Home)\n"
            f"Distance: {distance}\n"
            f"Estimated Time: {duration} (with traffic)\n\n"
            f"{step_summary}"
        )
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Route API error: {e}")
        await update.message.reply_text("Route calculation failed. Check logs or try again.")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /remind 08:30 Your message")
        return
    time_str = context.args[0]
    message = " ".join(context.args[1:])
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await update.message.reply_text("Time must be HH:MM (24h)")
        return

    now = datetime.now(TIMEZONE)
    target = datetime.strptime(f"{now.date()} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=TIMEZONE)
    if target < now:
        target += timedelta(days=1)
    delay = (target - now).total_seconds()

    context.job_queue.run_once(
        callback=lambda ctx: ctx.bot.send_message(chat_id=update.effective_chat.id, text=f"Reminder: {message}"),
        when=delay,
        name=f"remind_{update.effective_chat.id}"
    )
    await update.message.reply_text(f"Reminder set for {time_str} tomorrow.\n\"{message}\"")

async def thought_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /thought Your thought here")
        return
    text = " ".join(context.args)
    save_thought(update.effective_chat.id, text)
    await update.message.reply_text(f"Saved at {datetime.now(TIMEZONE).strftime('%H:%M')}\n\n“{text}”")

async def today_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thoughts = get_thoughts(update.effective_chat.id, today_only=True)
    if not thoughts:
        await update.message.reply_text("No thoughts today yet.")
        return
    msg = f"Today's thoughts ({datetime.now(TIMEZONE).date()}):\n\n"
    for t in thoughts:
        msg += f"• {datetime.fromisoformat(t['time']).strftime('%H:%M')} — {t['text']}\n"
    await update.message.reply_text(msg)

async def all_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thoughts = get_thoughts(update.effective_chat.id)
    if not thoughts:
        await update.message.reply_text("No thoughts saved yet.")
        return
    msg = f"Last {len(thoughts)} thoughts:\n\n"
    for t in thoughts:
        msg += f"{datetime.fromisoformat(t['time']).strftime('%Y-%m-%d %H:%M')} → {t['text']}\n"
    await update.message.reply_text(msg)

async def motivate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"“{random.choice(QUOTES)}”")

def main():
    init_db()
    if not TOKEN:
        raise ValueError("BOT_TOKEN not set!")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("thought", thought_command))
    application.add_handler(CommandHandler("today", today_thoughts))
    application.add_handler(CommandHandler("allthoughts", all_thoughts))
    application.add_handler(CommandHandler("motivate", motivate))
    application.add_handler(CommandHandler("check", check_route))  # New command

    # Start web server in background
    Thread(target=run_web_server, daemon=True).start()

    print("Bot running 24/7 on Koyeb with route check!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
