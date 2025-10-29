# bot.py
import os
import logging 
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

# Load env vars (works on Railway automatically)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

PAY_LINK = "https://2ph999.vip/?pid=96253491"
SHARE_LINK = "https://telegram.me/share/url?url=https%3A%2F%2Ft.me%2FFREE30DAYSVIPbot&text=LIBRE%20ATABS%20LEAKS%20DITO%20🤪🤪"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "vip.db"

# =========================
# Database setup & helpers
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            paid INTEGER DEFAULT 0,
            shared INTEGER DEFAULT 0,
            vip_until TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_user(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT paid, shared, vip_until FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"paid": False, "shared": False, "vip_until": None}
    paid, shared, vip_until = row
    return {"paid": bool(paid), "shared": bool(shared), "vip_until": vip_until}

def update_user(telegram_id, username, field):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (telegram_id, username))
    c.execute(f"UPDATE users SET {field} = 1 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def approve_user(telegram_id, days=30):
    until = datetime.utcnow() + timedelta(days=days)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET vip_until = ? WHERE telegram_id = ?", (until.isoformat(), telegram_id))
    conn.commit()
    conn.close()
    return until.isoformat()

# =========================
# Command Handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"Yo {user.first_name}! 🔥\n\n"
        "Gusto mo ng FREE VIP ACCESS (30 days)? Sundin lang ’tong steps:\n\n"
        "1️⃣ SIGNUP & CASHIN — gamitin ang button sa baba.\n"
        "2️⃣ SHARE ang bot sa mga tropa.\n"
        "3️⃣ I-chat ako ulit para ma-approve ni admin.\n\n"
        "📢 *Get VIP access for 30 days on our exclusive channels — more than 10,000 videos, photos & files leaks.*\n\n"
        "Piliin mo ang action sa baba ⬇️"
    )
    keyboard = [
        [InlineKeyboardButton("🪙 SIGNUP & PAY", url=PAY_LINK)],
        [InlineKeyboardButton("✅ I PAID", callback_data="paid")],
        [InlineKeyboardButton("📤 SHARE BOT", url=SHARE_LINK)],
        [InlineKeyboardButton("✅ DONE SHARING", callback_data="shared")],
        [InlineKeyboardButton("ℹ️ CHECK STATUS", callback_data="status")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    data = query.data

    if data == "paid":
        update_user(user.id, user.username or user.full_name, "paid")
        await query.edit_message_text("✅ Payment logged! Now share the bot and click *DONE SHARING*.", parse_mode="Markdown")
    elif data == "shared":
        update_user(user.id, user.username or user.full_name, "shared")
        await query.edit_message_text(
            "✅ Noted! Ngayon, maghintay ng admin approval. "
            "Kapag approved, may 30 days VIP access ka agad. 💎",
            parse_mode="Markdown"
        )
    elif data == "status":
        st = get_user(user.id)
        vip = st['vip_until'] or "Not VIP yet"
        await query.edit_message_text(
            f"📊 Status for @{user.username or user.full_name}\n"
            f"Paid: {'✅' if st['paid'] else '❌'}\n"
            f"Shared: {'✅' if st['shared'] else '❌'}\n"
            f"VIP Until: {vip}", parse_mode="Markdown"
        )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /approve <telegram_id> [days]"""
    user = update.effective_user
    if user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("🚫 Not authorized.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /approve <telegram_id> [days]")
        return
    try:
        tid = int(args[0])
        days = int(args[1]) if len(args) > 1 else 30
        until = approve_user(tid, days)
        await update.message.reply_text(f"✅ Approved {tid} for {days} days (until {until})")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /check <telegram_id>"""
    user = update.effective_user
    if user.id != ADMIN_TELEGRAM_ID:
        await update.message.reply_text("🚫 Not authorized.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /check <telegram_id>")
        return
    try:
        tid = int(args[0])
        st = get_user(tid)
        await update.message.reply_text(str(st))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    st = get_user(user.id)
    vip = st['vip_until'] or "Not VIP yet"
    await update.message.reply_text(
        f"📊 Status:\nPaid: {'✅' if st['paid'] else '❌'}\nShared: {'✅' if st['shared'] else '❌'}\nVIP Until: {vip}"
    )

def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CallbackQueryHandler(callback_handler))
    logger.info("🤖 Bot is live!")
    app.run_polling()

if __name__ == "__main__":
    main()
