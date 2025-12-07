# bot.py (Enhanced with SQLite Persistence for Koyeb Deployment)
import os
import logging
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import random

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ------------------- Configuration -------------------
TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = ZoneInfo("Asia/Hong_Kong")
DB_PATH = "bot_data.db"  # SQLite file; persists on ephemeral disk
# -----------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Motivational quotes
QUOTES = [
    "The best time to plant a tree was 20 years ago. The second best time is now.",
    "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    "Believe you can and you're halfway there.",
    "Don't watch the clock; do what it does. Keep going.",
    "Everything you've ever wanted is on the other side of fear.",
    "The only way to do great work is to love what you do.",
    "Your limitation—it's only your imagination.",
    "Great things never come from comfort zones.",
]

# ------------------- Database Setup -------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thoughts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            timestamp TEXT,
            text TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            time_str TEXT,
            message TEXT,
            active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def save_thought(chat_id: int, text: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = datetime.now(TIMEZONE).isoformat()
    cursor.execute("INSERT INTO thoughts (chat_id, timestamp, text) VALUES (?, ?, ?)",
                   (chat_id, timestamp, text.strip()))
    conn.commit()
    conn.close()

def get_thoughts(chat_id: int, date_filter=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if date_filter:
        today = date_filter.date().isoformat()  # YYYY-MM-DD
        cursor.execute("""
            SELECT timestamp, text FROM thoughts 
            WHERE chat_id = ? AND DATE(timestamp) = ? 
            ORDER BY timestamp
        """, (chat_id, today))
    else:
        cursor.execute("""
            SELECT timestamp, text FROM thoughts 
            WHERE chat_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 20
        """, (chat_id,))
    results = [{"time": row[0], "text": row[1]} for row in cursor.fetchall()]
    conn.close()
    return results

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text=f"Reminder: {job.data}")

# ------------------- Commands -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I am your personal reminder & thought journal bot with persistent storage.\n\n"
        "Commands:\n"
        "/remind <time> <message>  → e.g. /remind 08:30 Wake up and conquer the day!\n"
        "/thought <your text>       → Record a thought/journal entry\n"
        "/today                     → Show today’s thoughts\n"
        "/allthoughts               → Show all your thoughts\n"
        "/motivate                  → Get a random motivational quote\n"
        "/help                      → Show this message"
    )

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /remind 08:30 Do something great")
        return

    time_str = context.args[0]
    message = " ".join(context.args[1:])

    try:
        datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        await update.message.reply_text("Time format must be HH:MM (24h)")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO reminders (chat_id, time_str, message) VALUES (?, ?, ?)",
                   (update.effective_chat.id, time_str, message))
    conn.commit()
    conn.close()

    # Schedule one-time reminder; for recurring, extend with daily job checks
    now = datetime.now(TIMEZONE)
    reminder_time = datetime.strptime(time_str, "%H:%M").time()
    reminder_dt = datetime.combine(now.date(), reminder_time, tzinfo=TIMEZONE)
    if reminder_dt < now:
        reminder_dt += timedelta(days=1)
    delay = (reminder_dt - now).total_seconds()

    context.job_queue.run_once(send_reminder, when=delay, chat_id=update.effective_chat.id, data=message)

    await update.message.reply_text(f"Reminder set for {time_str}!\n\"{message}\"")

async def thought_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /thought Today I feel grateful because...")
        return

    text = " ".join(context.args)
    save_thought(update.effective_chat.id, text)
    hk_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    await update.message.reply_text(f"Thought saved at {hk_time}\n\n“{text}”")

async def today_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(TIMEZONE)
    user_thoughts = get_thoughts(update.effective_chat.id, today)
    if not user_thoughts:
        await update.message.reply_text("No thoughts recorded today yet.")
        return

    response = f"Your thoughts today ({today.strftime('%Y-%m-%d')}):\n\n"
    for t in user_thoughts:
        time_str = datetime.fromisoformat(t["time"]).strftime("%H:%M")
        response += f"• {time_str} — {t['text']}\n"
    await update.message.reply_text(response)

async def all_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_thoughts = get_thoughts(update.effective_chat.id)
    if not user_thoughts:
        await update.message.reply_text("No thoughts recorded yet.")
        return

    response = f"All your thoughts ({len(user_thoughts)} total):\n\n"
    for t in user_thoughts:
        date_str = datetime.fromisoformat(t["time"]).strftime("%Y-%m-%d %H:%M")
        response += f"{date_str} → {t['text']}\n"
    await update.message.reply_text(response)

async def motivate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quote = random.choice(QUOTES)
    await update.message.reply_text(f"“{quote}”")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ------------------- Main -------------------
def main():
    init_db()  # Initialize database on startup
    if not TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required.")
    
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("thought", thought_command))
    app.add_handler(CommandHandler("today", today_thoughts))
    app.add_handler(CommandHandler("allthoughts", all_thoughts))
    app.add_handler(CommandHandler("motivate", motivate))

    print("Bot is running 24/7 with persistent storage...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
