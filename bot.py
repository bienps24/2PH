import os
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
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
VIP_CHANNEL_LINK = "https://t.me/+quScJu8EG2dlYTk1"
WELCOME_IMAGE = "welcome.jpg"

logging.basicConfig(format="%(asctime)s - [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "vip.db"
DELETE_AFTER = 15  # seconds


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


def get_total_users():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count


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


def approve_user(telegram_id, days=30):
    until = datetime.utcnow() + timedelta(days=days)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("UPDATE users SET vip_until = ?, paid = 1 WHERE telegram_id = ?", (until.isoformat(), telegram_id))
    conn.commit()
    conn.close()
    return until.strftime("%Y-%m-%d")


# =========================
# AUTO DELETE HELPER
# =========================
async def auto_delete(message):
    await asyncio.sleep(DELETE_AFTER)
    try:
        await message.delete()
    except:
        pass


# =========================
# USER COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username or user.full_name

    # add to database if new user
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (telegram_id, username) VALUES (?, ?)", (user.id, username))
    conn.commit()
    conn.close()

    # Send welcome image if present
    if os.path.exists(WELCOME_IMAGE):
        img = await update.message.reply_photo(photo=InputFile(WELCOME_IMAGE))
        asyncio.create_task(auto_delete(img))

    text = (
        f"👋 Hi **{username}!**\n\n"
        "🎁 *Gusto mo ng 30 DAYS FREE VIP ACCESS?* Sundin lang ang mga hakbang:\n\n"
        "1️⃣ **Mag-Register at Mag Laro** gamit ang button sa ibaba.\n"
        "2️⃣ **I-Share ang Bot** sa mga tropa.\n"
        "3️⃣ **Chat @PinayWalkerManilaBot** para ma-approve ni admin.\n\n"
        "💎 *Pag na-approve ka, may 30-Days VIP Access ka sa exclusive channel — 10,000+ leaks, photos, at videos!*\n\n"
        f"🔗 **VIP Channel Preview:**\n👉 {VIP_CHANNEL_LINK}\n\n"
        "👇 Piliin ang action sa ibaba:"
    )

    keyboard = [
        [InlineKeyboardButton("🪙 Step 1: REGISTER", url=PAY_LINK)],
        [InlineKeyboardButton("📤 Step 2: SHARE 0/3", url=SHARE_LINK)],
        [InlineKeyboardButton("ℹ️ CHECK STATUS", callback_data="status")],
    ]

    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    asyncio.create_task(auto_delete(msg))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    username = user.username or user.full_name
    await query.answer()

    data = query.data
    if data == "status":
        st = get_user(user.id)
        vip = st['vip_until'] or "❌ Not VIP yet"

        msg = (
            f"📊 **Status for {username}**\n"
            f"Registered: {'✅' if st['paid'] else '❌'}\n"
            f"Shared: {'✅' if st['shared'] else '❌'}\n"
            f"VIP Until: {vip}\n\n"
            f"🔗 *VIP Channel:* {VIP_CHANNEL_LINK}\n\n"
            "💬 Once approved, you’ll get your VIP privileges automatically."
        )
    else:
        msg = "Unknown action."

    m = await query.edit_message_text(msg, parse_mode="Markdown")
    asyncio.create_task(auto_delete(m))


# =========================
# ADMIN COMMANDS
# =========================
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        msg = await update.message.reply_text("🚫 Not authorized.")
        asyncio.create_task(auto_delete(msg))
        return

    args = context.args
    if not args:
        msg = await update.message.reply_text("Usage: /approve <telegram_id> [days]")
        asyncio.create_task(auto_delete(msg))
        return

    try:
        tid = int(args[0])
        days = int(args[1]) if len(args) > 1 else 30
        until = approve_user(tid, days)

        msg = await update.message.reply_text(f"✅ Approved `{tid}` for {days} days (until {until})", parse_mode="Markdown")
        asyncio.create_task(auto_delete(msg))

        await context.bot.send_message(
            tid,
            f"🎉 Congratulations! You now have **{days} days VIP Access!**\n\n"
            f"👉 Access VIP content here: {VIP_CHANNEL_LINK}"
        )

    except Exception as e:
        msg = await update.message.reply_text(f"⚠️ Error: {e}")
        asyncio.create_task(auto_delete(msg))


async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        msg = await update.message.reply_text("🚫 Not authorized.")
        asyncio.create_task(auto_delete(msg))
        return

    if not context.args:
        msg = await update.message.reply_text("Usage: /pin <announcement message>")
        asyncio.create_task(auto_delete(msg))
        return

    announcement = " ".join(context.args)
    msg = await update.message.reply_text(f"📌 *Announcement:*\n{announcement}", parse_mode="Markdown")
    await msg.pin()
    asyncio.create_task(auto_delete(msg))


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        msg = await update.message.reply_text("🚫 Not authorized.")
        asyncio.create_task(auto_delete(msg))
        return

    if not context.args:
        msg = await update.message.reply_text("Usage: /broadcast <message>")
        asyncio.create_task(auto_delete(msg))
        return

    announcement = " ".join(context.args)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()

    sent_count = 0
    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📣 *Announcement:*\n{announcement}",
                parse_mode="Markdown"
            )
            sent_count += 1
            await asyncio.sleep(0.3)
        except:
            pass

    msg = await update.message.reply_text(f"✅ Broadcast complete!\n📬 Sent to {sent_count} users.")
    asyncio.create_task(auto_delete(msg))


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_TELEGRAM_ID:
        msg = await update.message.reply_text("🚫 Not authorized.")
        asyncio.create_task(auto_delete(msg))
        return

    total = get_total_users()
    msg = await update.message.reply_text(f"👥 Total bot users: **{total}**", parse_mode="Markdown")
    asyncio.create_task(auto_delete(msg))


# =========================
# MAIN APP
# =========================
def main():
    init_db()
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not found in environment variables.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("broadcast", broadcast_message))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("🤖 Bot is live and running...")
    app.run_polling()


if __name__ == "__main__":
    main()
