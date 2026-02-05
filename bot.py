"""
VIP Access Telegram Bot
A professional bot for managing VIP memberships with registration and sharing mechanics.
"""

import os
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional, Dict, List
from dataclasses import dataclass

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from telegram.error import TelegramError
from dotenv import load_dotenv


# =========================
# CONFIGURATION
# =========================
@dataclass
class BotConfig:
    """Bot configuration settings"""
    bot_token: str
    admin_telegram_id: int
    pay_link: str = "https://2ph999.vip/?pid=96253491"
    share_link: str = "https://telegram.me/share/url?url=https%3A%2F%2Ft.me%2FFREE30DAYSVIPbot&text=LIBRE%20ATABS%20LEAKS%20DITO%20🤪🤪"
    vip_channel_link: str = "https://t.me/+MMRjUFZqsmpmN2Vl"
    welcome_image: str = "welcome.jpg"
    db_path: str = "vip.db"
    delete_after: int = 20
    default_vip_days: int = 30
    broadcast_delay: float = 0.5  # Delay between broadcast messages


def load_config() -> BotConfig:
    """Load configuration from environment variables"""
    load_dotenv()
    
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("❌ BOT_TOKEN not found in environment variables!")
    
    admin_id = os.getenv("ADMIN_TELEGRAM_ID", "0")
    try:
        admin_telegram_id = int(admin_id)
    except ValueError:
        raise ValueError("❌ ADMIN_TELEGRAM_ID must be a valid integer!")
    
    return BotConfig(
        bot_token=bot_token,
        admin_telegram_id=admin_telegram_id
    )


# =========================
# LOGGING SETUP
# =========================
def setup_logging():
    """Configure logging with better formatting"""
    logging.basicConfig(
        format="%(asctime)s - [%(levelname)s] %(name)s - %(message)s",
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("bot.log", encoding="utf-8")
        ]
    )
    # Reduce telegram library verbosity
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger(__name__)


logger = setup_logging()


# =========================
# DATABASE MANAGER
# =========================
class DatabaseManager:
    """Handle all database operations with proper connection management"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def init_db(self):
        """Initialize database with required tables"""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    paid INTEGER DEFAULT 0,
                    shared INTEGER DEFAULT 0,
                    vip_until TEXT,
                    last_activity TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    action TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                )
            """)
            
            conn.commit()
        logger.info("✅ Database initialized successfully")
    
    def add_or_update_user(self, telegram_id: int, username: str, first_name: str):
        """Add new user or update existing user information"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_activity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_activity = excluded.last_activity
            """, (telegram_id, username, first_name, datetime.utcnow().isoformat()))
            conn.commit()
    
    def get_user(self, telegram_id: int) -> Dict:
        """Get user information"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT paid, shared, vip_until FROM users WHERE telegram_id = ?",
                (telegram_id,)
            ).fetchone()
            
            if not row:
                return {"paid": False, "shared": False, "vip_until": None}
            
            return {
                "paid": bool(row["paid"]),
                "shared": bool(row["shared"]),
                "vip_until": row["vip_until"]
            }
    
    def approve_user(self, telegram_id: int, days: int = 30) -> str:
        """Approve user for VIP access"""
        until = datetime.utcnow() + timedelta(days=days)
        
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET vip_until = ?, paid = 1 WHERE telegram_id = ?",
                (until.isoformat(), telegram_id)
            )
            conn.execute(
                "INSERT INTO activity_log (telegram_id, action) VALUES (?, ?)",
                (telegram_id, f"Approved for {days} days")
            )
            conn.commit()
        
        return until.strftime("%B %d, %Y")
    
    def mark_shared(self, telegram_id: int):
        """Mark user as having shared the bot"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE users SET shared = 1 WHERE telegram_id = ?",
                (telegram_id,)
            )
            conn.commit()
    
    def get_total_users(self) -> int:
        """Get total number of users"""
        with self.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
            return count["count"]
    
    def get_all_user_ids(self) -> List[int]:
        """Get all user telegram IDs for broadcasting"""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT telegram_id FROM users").fetchall()
            return [row["telegram_id"] for row in rows]
    
    def get_vip_users_count(self) -> int:
        """Get count of active VIP users"""
        with self.get_connection() as conn:
            now = datetime.utcnow().isoformat()
            count = conn.execute(
                "SELECT COUNT(*) as count FROM users WHERE vip_until > ?",
                (now,)
            ).fetchone()
            return count["count"]
    
    def is_vip_active(self, telegram_id: int) -> bool:
        """Check if user's VIP status is still active"""
        user = self.get_user(telegram_id)
        if not user["vip_until"]:
            return False
        
        try:
            vip_until = datetime.fromisoformat(user["vip_until"])
            return vip_until > datetime.utcnow()
        except ValueError:
            return False


# =========================
# MESSAGE UTILITIES
# =========================
class MessageFormatter:
    """Format messages with consistent styling"""
    
    @staticmethod
    def welcome_message(username: str, vip_link: str) -> str:
        """Format welcome message"""
        return (
            f"👋 Kumusta, **{username}!**\n\n"
            "🎁 **Libre 30 Days VIP Access!**\n"
            "Sumunod lang sa simpleng mga hakbang:\n\n"
            "**Hakbang 1:** Mag-register at maglaro\n"
            "↳ _I-click ang 'Register' button sa baba_\n\n"
            "**Hakbang 2:** I-share ang bot sa 3 kaibigan\n"
            "↳ _I-click ang 'Share' button para i-share_\n\n"
            "**Hakbang 3:** Mag-antay ng approval\n"
            "↳ _Pakiusap i-message si @PinayWalkerManilaBot_\n\n"
            "💎 **Pag approved ka na:**\n"
            f"• Access sa VIP Channel: {vip_link}\n"
            "• 10,000+ exclusive leaks\n"
            "• Premium photos at videos\n"
            "• 30 days ng walang bayad!\n\n"
            "👇 Simulan na ngayon:"
        )
    
    @staticmethod
    def status_message(username: str, paid: bool, shared: bool, vip_until: Optional[str], vip_link: str) -> str:
        """Format status check message"""
        vip_status = "❌ Hindi pa VIP"
        if vip_until:
            try:
                vip_date = datetime.fromisoformat(vip_until)
                if vip_date > datetime.utcnow():
                    vip_status = f"✅ Active hanggang {vip_date.strftime('%B %d, %Y')}"
                else:
                    vip_status = "⚠️ Expired na"
            except ValueError:
                pass
        
        return (
            f"📊 **Status ni {username}**\n\n"
            f"🎮 Registration: {'✅ Complete' if paid else '❌ Pending'}\n"
            f"📤 Sharing: {'✅ Complete' if shared else '❌ Pending'}\n"
            f"💎 VIP Access: {vip_status}\n\n"
            f"🔗 **VIP Channel:** {vip_link}\n\n"
            "💬 _Kapag approved ka na, automatic makakakuha ka ng VIP access!_\n\n"
            "❓ May tanong? Message si @PinayWalkerManilaBot"
        )
    
    @staticmethod
    def help_message() -> str:
        """Format help message"""
        return (
            "📖 **Available Commands**\n\n"
            "**Para sa lahat:**\n"
            "• /start - Simulan ang bot\n"
            "• /status - Tingnan ang iyong status\n"
            "• /help - Tingnan ang help menu\n\n"
            "**Para sa Admin:**\n"
            "• /approve <user_id> [days] - Approve user\n"
            "• /stats - View statistics\n"
            "• /broadcast <message> - Send message sa lahat\n"
            "• /pin <message> - Pin announcement\n\n"
            "❓ Need help? Contact @PinayWalkerManilaBot"
        )


# =========================
# AUTO DELETE UTILITY
# =========================
async def auto_delete_message(message, delay: int):
    """Auto-delete message after specified delay"""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except TelegramError as e:
        logger.debug(f"Could not delete message: {e}")


# =========================
# USER COMMAND HANDLERS
# =========================
class UserHandlers:
    """Handlers for user commands"""
    
    def __init__(self, db: DatabaseManager, config: BotConfig):
        self.db = db
        self.config = config
        self.formatter = MessageFormatter()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        username = user.username or user.first_name or "User"
        
        # Update user in database
        self.db.add_or_update_user(user.id, user.username, user.first_name)
        logger.info(f"User {user.id} ({username}) started the bot")
        
        # Send welcome image if exists
        if os.path.exists(self.config.welcome_image):
            try:
                with open(self.config.welcome_image, 'rb') as photo:
                    img_msg = await update.message.reply_photo(
                        photo=photo,
                        caption="🎉 Welcome to VIP Access Bot!"
                    )
                    asyncio.create_task(auto_delete_message(img_msg, self.config.delete_after))
            except Exception as e:
                logger.error(f"Error sending welcome image: {e}")
        
        # Send welcome message with buttons
        text = self.formatter.welcome_message(username, self.config.vip_channel_link)
        
        keyboard = [
            [InlineKeyboardButton("🎮 Step 1: REGISTER & PLAY", url=self.config.pay_link)],
            [InlineKeyboardButton("📤 Step 2: SHARE TO 3 FRIENDS", url=self.config.share_link)],
            [InlineKeyboardButton("✅ Step 3: CHECK STATUS", callback_data="status")],
            [InlineKeyboardButton("❓ HELP & INFO", callback_data="help")]
        ]
        
        msg = await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 10))
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user = update.effective_user
        username = user.username or user.first_name or "User"
        
        user_data = self.db.get_user(user.id)
        text = self.formatter.status_message(
            username,
            user_data["paid"],
            user_data["shared"],
            user_data["vip_until"],
            self.config.vip_channel_link
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Status", callback_data="status")],
            [InlineKeyboardButton("🏠 Back to Start", callback_data="back_to_start")]
        ]
        
        msg = await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 5))
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        text = self.formatter.help_message()
        
        keyboard = [[InlineKeyboardButton("🏠 Back to Start", callback_data="back_to_start")]]
        
        msg = await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 5))


# =========================
# CALLBACK QUERY HANDLER
# =========================
class CallbackHandler:
    """Handle callback queries from inline buttons"""
    
    def __init__(self, db: DatabaseManager, config: BotConfig):
        self.db = db
        self.config = config
        self.formatter = MessageFormatter()
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main callback handler"""
        query = update.callback_query
        user = query.from_user
        username = user.username or user.first_name or "User"
        
        await query.answer()
        
        data = query.data
        
        if data == "status":
            await self._handle_status(query, user, username)
        elif data == "help":
            await self._handle_help(query)
        elif data == "back_to_start":
            await self._handle_back_to_start(query, username)
        else:
            await query.edit_message_text("❌ Unknown action.")
    
    async def _handle_status(self, query, user, username):
        """Handle status callback"""
        user_data = self.db.get_user(user.id)
        text = self.formatter.status_message(
            username,
            user_data["paid"],
            user_data["shared"],
            user_data["vip_until"],
            self.config.vip_channel_link
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="status")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def _handle_help(self, query):
        """Handle help callback"""
        text = self.formatter.help_message()
        
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    
    async def _handle_back_to_start(self, query, username):
        """Handle back to start callback"""
        text = self.formatter.welcome_message(username, self.config.vip_channel_link)
        
        keyboard = [
            [InlineKeyboardButton("🎮 Step 1: REGISTER & PLAY", url=self.config.pay_link)],
            [InlineKeyboardButton("📤 Step 2: SHARE TO 3 FRIENDS", url=self.config.share_link)],
            [InlineKeyboardButton("✅ Step 3: CHECK STATUS", callback_data="status")],
            [InlineKeyboardButton("❓ HELP & INFO", callback_data="help")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )


# =========================
# ADMIN COMMAND HANDLERS
# =========================
class AdminHandlers:
    """Handlers for admin commands"""
    
    def __init__(self, db: DatabaseManager, config: BotConfig):
        self.db = db
        self.config = config
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.config.admin_telegram_id
    
    async def approve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve user for VIP access"""
        if not self.is_admin(update.effective_user.id):
            msg = await update.message.reply_text("🚫 **Access Denied:** Admin only command.")
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            return
        
        args = context.args
        if not args:
            msg = await update.message.reply_text(
                "📋 **Usage:** `/approve <telegram_id> [days]`\n\n"
                "**Example:**\n"
                "`/approve 123456789 30`",
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            return
        
        try:
            telegram_id = int(args[0])
            days = int(args[1]) if len(args) > 1 else self.config.default_vip_days
            
            if days <= 0:
                raise ValueError("Days must be positive")
            
            until_date = self.db.approve_user(telegram_id, days)
            
            msg = await update.message.reply_text(
                f"✅ **User Approved!**\n\n"
                f"👤 User ID: `{telegram_id}`\n"
                f"📅 VIP Days: {days}\n"
                f"⏰ Valid Until: {until_date}",
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            
            # Notify user
            try:
                await context.bot.send_message(
                    telegram_id,
                    f"🎉 **Congratulations!**\n\n"
                    f"✅ Approved ka na para sa **{days} days VIP Access!**\n\n"
                    f"💎 **Access your VIP content here:**\n"
                    f"👉 {self.config.vip_channel_link}\n\n"
                    f"📅 Valid until: **{until_date}**\n\n"
                    f"Salamat at enjoy! 🎊",
                    parse_mode="Markdown"
                )
                logger.info(f"Notified user {telegram_id} of approval")
            except TelegramError as e:
                logger.error(f"Could not notify user {telegram_id}: {e}")
                await update.message.reply_text(
                    f"⚠️ User approved but notification failed: {e}",
                    parse_mode="Markdown"
                )
        
        except ValueError as e:
            msg = await update.message.reply_text(f"❌ **Invalid input:** {e}")
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
        except Exception as e:
            logger.error(f"Error approving user: {e}")
            msg = await update.message.reply_text(f"⚠️ **Error:** {e}")
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        if not self.is_admin(update.effective_user.id):
            msg = await update.message.reply_text("🚫 **Access Denied:** Admin only command.")
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            return
        
        total_users = self.db.get_total_users()
        vip_users = self.db.get_vip_users_count()
        
        text = (
            "📊 **Bot Statistics**\n\n"
            f"👥 Total Users: **{total_users}**\n"
            f"💎 Active VIP Users: **{vip_users}**\n"
            f"👤 Regular Users: **{total_users - vip_users}**\n\n"
            f"📈 VIP Conversion: **{(vip_users/total_users*100) if total_users > 0 else 0:.1f}%**"
        )
        
        msg = await update.message.reply_text(text, parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 10))
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users"""
        if not self.is_admin(update.effective_user.id):
            msg = await update.message.reply_text("🚫 **Access Denied:** Admin only command.")
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            return
        
        if not context.args:
            msg = await update.message.reply_text(
                "📋 **Usage:** `/broadcast <message>`\n\n"
                "**Example:**\n"
                "`/broadcast Happy New Year to all VIP members!`",
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            return
        
        announcement = " ".join(context.args)
        user_ids = self.db.get_all_user_ids()
        
        status_msg = await update.message.reply_text(
            f"📡 **Broadcasting...**\n"
            f"Total recipients: {len(user_ids)}\n\n"
            f"_Please wait..._",
            parse_mode="Markdown"
        )
        
        sent_count = 0
        failed_count = 0
        
        for user_id in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📣 **Announcement**\n\n{announcement}",
                    parse_mode="Markdown"
                )
                sent_count += 1
                await asyncio.sleep(self.config.broadcast_delay)
            except TelegramError as e:
                logger.debug(f"Failed to send to {user_id}: {e}")
                failed_count += 1
        
        await status_msg.edit_text(
            f"✅ **Broadcast Complete!**\n\n"
            f"📬 Successfully sent: **{sent_count}**\n"
            f"❌ Failed: **{failed_count}**\n"
            f"📊 Success rate: **{(sent_count/(sent_count+failed_count)*100) if (sent_count+failed_count) > 0 else 0:.1f}%**",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete_message(status_msg, self.config.delete_after + 10))
    
    async def pin_announcement(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pin an announcement in the chat"""
        if not self.is_admin(update.effective_user.id):
            msg = await update.message.reply_text("🚫 **Access Denied:** Admin only command.")
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            return
        
        if not context.args:
            msg = await update.message.reply_text(
                "📋 **Usage:** `/pin <message>`\n\n"
                "**Example:**\n"
                "`/pin Server maintenance tonight at 10 PM`",
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            return
        
        announcement = " ".join(context.args)
        
        try:
            msg = await update.message.reply_text(
                f"📌 **Pinned Announcement**\n\n{announcement}",
                parse_mode="Markdown"
            )
            await msg.pin(disable_notification=False)
            logger.info(f"Pinned announcement by admin {update.effective_user.id}")
        except TelegramError as e:
            logger.error(f"Could not pin message: {e}")
            error_msg = await update.message.reply_text(
                f"⚠️ **Error pinning message:** {e}"
            )
            asyncio.create_task(auto_delete_message(error_msg, self.config.delete_after))


# =========================
# ERROR HANDLER
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ **Oops! Something went wrong.**\n\n"
                "Please try again later or contact support.",
                parse_mode="Markdown"
            )
        except TelegramError:
            pass


# =========================
# MAIN APPLICATION
# =========================
def main():
    """Initialize and run the bot"""
    try:
        # Load configuration
        config = load_config()
        logger.info("✅ Configuration loaded successfully")
        
        # Initialize database
        db = DatabaseManager(config.db_path)
        logger.info("✅ Database initialized successfully")
        
        # Initialize handlers
        user_handlers = UserHandlers(db, config)
        admin_handlers = AdminHandlers(db, config)
        callback_handler = CallbackHandler(db, config)
        
        # Build application
        app = Application.builder().token(config.bot_token).build()
        
        # Add user command handlers
        app.add_handler(CommandHandler("start", user_handlers.start))
        app.add_handler(CommandHandler("status", user_handlers.status))
        app.add_handler(CommandHandler("help", user_handlers.help_command))
        
        # Add admin command handlers
        app.add_handler(CommandHandler("approve", admin_handlers.approve))
        app.add_handler(CommandHandler("stats", admin_handlers.stats))
        app.add_handler(CommandHandler("broadcast", admin_handlers.broadcast))
        app.add_handler(CommandHandler("pin", admin_handlers.pin_announcement))
        
        # Add callback query handler
        app.add_handler(CallbackQueryHandler(callback_handler.handle))
        
        # Add error handler
        app.add_error_handler(error_handler)
        
        logger.info("🤖 Bot is starting...")
        logger.info(f"👤 Admin ID: {config.admin_telegram_id}")
        logger.info("✅ All handlers registered successfully")
        logger.info("🚀 Bot is now running! Press Ctrl+C to stop.")
        
        # Start polling
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.critical(f"❌ Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    main()
