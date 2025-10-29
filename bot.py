import os
import logging
import sqlite3
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from dotenv import load_dotenv

# =========================
# ENV + CONFIG
# =========================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

PAY_LINK = "https://2ph999.vip/?pid=96253491"
SHARE_LINK = "https://telegram.me/share/url?url=https%3A%2F%2Ft.me%2FFREE30DAYSVIPbot&text=LIBRE%20ATABS%20LEAKS%20DITO%20🤪🤪"

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_PATH = "vip.db"


# =========================
# DATABASE UTILITIES
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT paid, shared, vip_until FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"paid": False, "shared": False, "vip_until": None}
    paid, shared, vip_until = row
    return {"paid": bool(paid), "shared": bool(shared), "vip_until": vip_until}


def update_user(telegram_id, username, field):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (telegram_id, username))
    c.execute(f"UPDATE users SET {field} = 1 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()


def approve_user(telegram_id, days=30):
    until = datetime.utcnow() + timedelta(days=days)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("UPDATE users SET vip_until = ? WHERE telegram_id = ?", (until.isoformat(), telegram_id))
    conn.commit()
    conn.close()
    return until.strftime("%Y-%m-%d")


# =========================
# USER COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or user.full_name

    text = (
        f"👋 Hi **{username}!**\n\n"
        "🎁 *Gusto mo ng 30 DAYS FREE VIP ACCESS?* Sundin lang ang mga hakbang sa ibaba:\n\n"
        "1️⃣ **Mag-Signup at Mag-Cash-In** gamit ang button.\n"
        "2️⃣ **I-Share ang Bot** sa mga tropa.\n"
        "3️⃣ **Chat @PinayWalkerManilaBot** para ma-approve ni admin.\n\n"
        "💎 *Get VIP access for 30 days to our exclusive channels — 10,000+ videos, photos, and leaks!*\n"
    )

    keyboard = [
        [InlineKeyboardButton("🪙 SIGNUP & CASH-IN", url=PAY_LINK)],
        [InlineKeyboardButton("✅ I PAID", callback_data="paid")],
        [InlineKeyboardButton("📤 SHARE BOT", url=SHARE_LINK)],
        [InlineKeyboardButton("✅ DONE SHARING", callback_data="shared")],
        [InlineKeyboardButton("ℹ️ CHECK STATUS", callback_data="status")],
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    username = user.username or user.full_name
    await query.answer()

    data = query.data
    if data == "paid":
        update_user(user.id, username, "paid")
        msg = "💰 Payment recorded!\nNow share the bot and tap **DONE SHARING** after."
    elif data == "shared":
        update_user(user.id, username, "shared")
        msg = (
            "📤 Thanks for sharing!\n"
            "Please wait for admin approval — once approved, you’ll get **30 Days VIP Access** 💎"
        )
    elif data == "status":
        st = get_user(user.id)
        vip = st['vip_until'] or "❌ Not VIP yet"
        msg = (
            f"📊 **Status for {username}**\n"
            f"Paid: {'✅' if st['paid'] else '❌'}\n"
            f"Shared: {'✅' if st['shared'] else '❌'}\n"
            f"VIP Until: {vip}"
        )
    else:
        msg = "Unknown action."

    await query.edit_message_text(msg, parse_mode="Markdown")


# =========================
# ADMIN COMMANDS
# =========================
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"✅ Approved `{tid}` for {days} days (until {until})", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"📊 {st}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")


# =========================
# MAIN APP
# =========================
def main():
    init_db()
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not found in environment variables.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", start))  # alias
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("🤖 Bot is live and running...")
    app.run_polling()


if __name__ == "__main__":
    main()
