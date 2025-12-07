# bot.py
import os
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ------------------- Configuration -------------------
TOKEN = os.getenv("BOT_TOKEN")          # Set this in environment variables
TIMEZONE = ZoneInfo("Asia/Hong_Kong")   # Hong Kong time
# -----------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory storage (for free hosts; data resets on restart)
# For persistent storage, replace with SQLite or PostgreSQL later
reminders = []          # List of {"chat_id": int, "text": str, "time": str, "job": Job}
thoughts = {}           # {chat_id: [{"time": datetime, "text": str}, ...]}

# Motivational quotes (you can expand this list)
QUOTES = [
    "The best time to plant a tree was 20 years ago. The second best time is now.",
    "Success is not final, failure is not fatal: it is the courage to continue that counts.",
    "Believe you can and you're halfway there.",
    "Don’t watch the clock; do what it does. Keep going.",
    "Everything you’ve ever wanted is on the other side of fear.",
    "The only way to do great work is to love what you do.",
    "Your limitation—it's only your imagination.",
    "Great things never come from comfort zones.",
]

# ------------------- Helper Functions -------------------
def get_thoughts(chat_id: int):
    return thoughts.get(chat_id, [])

def save_thought(chat_id: int, text: str):
    if chat_id not in thoughts:
        thoughts[chat_id] = []
    thoughts[chat_id].append({
        "time": datetime.now(TIMEZONE),
        "text": text.strip()
    })

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text=f"Reminder: {job.data}")

# ------------------- Commands -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I am your personal reminder & thought journal bot.\n\n"
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
        reminder_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        await update.message.reply_text("Time format must be HH:MM (24h)")
        return

    now = datetime.now(TIMEZONE)
    reminder_dt = datetime.combine(now.date(), reminder_time, tzinfo=TIMEZONE)

    if reminder_dt < now:
        reminder_dt = reminder_dt.replace(day=reminder_dt.day + 1)  # tomorrow

    delay = (reminder_dt - now).total_seconds()

    job = context.job_queue.run_once(
        send_reminder,
        when=delay,
        chat_id=update.effective_chat.id,
        data=message,
        name=f"reminder_{update.effective_chat.id}"
    )

    reminders.append({
        "chat_id": update.effective_chat.id,
        "text": message,
        "time": time_str,
        "job": job
    })

    await update.message.reply_text(
        f"Reminder set for {time_str} every day!\n"
        f"\"{message}\""
    )

async def thought_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /thought Today I feel grateful because...")
        return

    text = " ".join(context.args)
    save_thought(update.effective_chat.id, text)
    hk_time = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    await update.message.reply_text(f"Thought saved at {hk_time}\n\n“{text}”")

async def today_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_thoughts = get_thoughts(update.effective_chat.id)
    today = datetime.now(TIMEZONE).date()
    todays = [t for t in user_thoughts if t["time"].date() == today]

    if not todays:
        await update.message.reply_text("No thoughts recorded today yet.")
        return

    response = f"Your thoughts today ({today.strftime('%Y-%m-%d')}):\n\n"
    for t in todays:
        time_str = t["time"].strftime("%H:%M")
        response += f"• {time_str} — {t['text']}\n"
    await update.message.reply_text(response)

async def all_thoughts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_thoughts = get_thoughts(update.effective_chat.id)
    if not user_thoughts:
        await update.message.reply_text("No thoughts recorded yet.")
        return

    response = f"All your thoughts ({len(user_thoughts)} total):\n\n"
    for t in user_thoughts[-20:]:  # Show last 20 to avoid spam
        date_str = t["time"].strftime("%Y-%m-%d %H:%M")
        response += f"{date_str} → {t['text']}\n"
    if len(user_thoughts) > 20:
        response += "\n... (showing last 20 entries)"
    await update.message.reply_text(response)

async def motivate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random
    quote = random.choice(QUOTES)
    await update.message.reply_text(f"“{quote}”")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ------------------- Main -------------------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CommandHandler("thought", thought_command))
    app.add_handler(CommandHandler("today", today_thoughts))
    app.add_handler(CommandHandler("allthoughts", all_thoughts))
    app.add_handler(CommandHandler("motivate", motivate))

    print("Bot is running 24/7...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
