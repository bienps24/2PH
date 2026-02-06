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
    pay_link: str = "https://PH95222.com/?pid=96253491"
    share_link: str = "https://telegram.me/share/url?url=https%3A%2F%2Ft.me%2Fpinaygroupchatbot&start=LIBRE%20ATABS%20LEAKS%20DITO%20🤪🤪"
    vip_channel_link: str = "https://t.me/+MMRjUFZqsmpmN2Vl"
    welcome_image: str = "welcome.jpg"
    db_path: str = "vip.db"
    delete_after: int = 9999
    default_vip_days: int = 30
    broadcast_delay: float = 0.5


def load_config() -> BotConfig:
    """Load configuration from environment variables"""
    load_dotenv()
    
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise ValueError("❌ BOT_TOKEN not found in environment variables!")
    
    admin_id = os.getenv("ADMIN_TELEGRAM_ID", "0")
    try:
        admin_telegram_id = int(admin_id)
        if admin_telegram_id == 0:
            logger.warning("⚠️ ADMIN_TELEGRAM_ID is set to 0 - admin features will be disabled")
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
    logging.getLogger("telegram").setLevel(logging.WARNING)
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
        try:
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
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    def add_or_update_user(self, telegram_id: int, username: str, first_name: str):
        """Add new user or update existing user information"""
        try:
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
        except Exception as e:
            logger.error(f"Error adding/updating user {telegram_id}: {e}")
    
    def get_user(self, telegram_id: int) -> Dict:
        """Get user information"""
        try:
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
        except Exception as e:
            logger.error(f"Error getting user {telegram_id}: {e}")
            return {"paid": False, "shared": False, "vip_until": None}
    
    def approve_user(self, telegram_id: int, days: int = 30) -> str:
        """Approve user for VIP access"""
        try:
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
        except Exception as e:
            logger.error(f"Error approving user {telegram_id}: {e}")
            raise
    
    def mark_shared(self, telegram_id: int):
        """Mark user as having shared the bot"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE users SET shared = 1 WHERE telegram_id = ?",
                    (telegram_id,)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error marking user {telegram_id} as shared: {e}")
    
    def get_total_users(self) -> int:
        """Get total number of users"""
        try:
            with self.get_connection() as conn:
                count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
                return count["count"]
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0
    
    def get_all_user_ids(self) -> List[int]:
        """Get all user telegram IDs for broadcasting"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute("SELECT telegram_id FROM users").fetchall()
                return [row["telegram_id"] for row in rows]
        except Exception as e:
            logger.error(f"Error getting user IDs: {e}")
            return []
    
    def get_vip_users_count(self) -> int:
        """Get count of active VIP users"""
        try:
            with self.get_connection() as conn:
                now = datetime.utcnow().isoformat()
                count = conn.execute(
                    "SELECT COUNT(*) as count FROM users WHERE vip_until > ?",
                    (now,)
                ).fetchone()
                return count["count"]
        except Exception as e:
            logger.error(f"Error getting VIP count: {e}")
            return 0
    
    def is_vip_active(self, telegram_id: int) -> bool:
        """Check if user's VIP status is still active"""
        try:
            user = self.get_user(telegram_id)
            if not user["vip_until"]:
                return False
            
            vip_until = datetime.fromisoformat(user["vip_until"])
            return vip_until > datetime.utcnow()
        except Exception as e:
            logger.error(f"Error checking VIP status for {telegram_id}: {e}")
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
            except (ValueError, TypeError):
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
            "• `/start` - Simulan ang bot\n"
            "• `/status` - Tingnan ang iyong status\n"
            "• `/help` - Tingnan ang help menu\n\n"
            "**Paano makakuha ng VIP:**\n"
            "1️⃣ Mag-register sa gaming site\n"
            "2️⃣ I-share ang bot sa 3 friends\n"
            "3️⃣ I-message si @PinayWalkerManilaBot\n"
            "4️⃣ Maghintay ng approval mula sa admin\n\n"
            "**Para sa Admin lang:**\n"
            "• `/approve <user_id> [days]` - Approve user\n"
            "• `/stats` - View statistics\n"
            "• `/broadcast <message>` - Send message sa lahat\n"
            "• `/pin <message>` - Pin announcement\n\n"
            "❓ **Need help?** Contact @PinayWalkerManilaBot"
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
    except Exception as e:
        logger.debug(f"Unexpected error deleting message: {e}")


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
        try:
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
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    def add_or_update_user(self, telegram_id: int, username: str, first_name: str):
        """Add new user or update existing user information"""
        try:
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
        except Exception as e:
            logger.error(f"Error adding/updating user {telegram_id}: {e}")
    
    def get_user(self, telegram_id: int) -> Dict:
        """Get user information"""
        try:
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
        except Exception as e:
            logger.error(f"Error getting user {telegram_id}: {e}")
            return {"paid": False, "shared": False, "vip_until": None}
    
    def approve_user(self, telegram_id: int, days: int = 30) -> str:
        """Approve user for VIP access"""
        try:
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
        except Exception as e:
            logger.error(f"Error approving user {telegram_id}: {e}")
            raise
    
    def mark_shared(self, telegram_id: int):
        """Mark user as having shared the bot"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE users SET shared = 1 WHERE telegram_id = ?",
                    (telegram_id,)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error marking user {telegram_id} as shared: {e}")
    
    def get_total_users(self) -> int:
        """Get total number of users"""
        try:
            with self.get_connection() as conn:
                count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
                return count["count"]
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0
    
    def get_all_user_ids(self) -> List[int]:
        """Get all user telegram IDs for broadcasting"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute("SELECT telegram_id FROM users").fetchall()
                return [row["telegram_id"] for row in rows]
        except Exception as e:
            logger.error(f"Error getting user IDs: {e}")
            return []
    
    def get_vip_users_count(self) -> int:
        """Get count of active VIP users"""
        try:
            with self.get_connection() as conn:
                now = datetime.utcnow().isoformat()
                count = conn.execute(
                    "SELECT COUNT(*) as count FROM users WHERE vip_until > ?",
                    (now,)
                ).fetchone()
                return count["count"]
        except Exception as e:
            logger.error(f"Error getting VIP count: {e}")
            return 0
    
    def is_vip_active(self, telegram_id: int) -> bool:
        """Check if user's VIP status is still active"""
        try:
            user = self.get_user(telegram_id)
            if not user["vip_until"]:
                return False
            
            vip_until = datetime.fromisoformat(user["vip_until"])
            return vip_until > datetime.utcnow()
        except Exception as e:
            logger.error(f"Error checking VIP status for {telegram_id}: {e}")
            return False


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
        try:
            user = update.effective_user
            username = user.username or user.first_name or "User"
            
            # Update user in database
            self.db.add_or_update_user(user.id, user.username or "", user.first_name or "User")
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
                    logger.warning(f"Could not send welcome image: {e}")
            
            # Send welcome message with buttons
            text = self.formatter.welcome_message(username, self.config.vip_channel_link)
            
            keyboard = [
                [InlineKeyboardButton("🎮 Step 1: REGISTER & PLAY", url=self.config.pay_link)],
                [InlineKeyboardButton("📤 Step 2: SHARE TO 3 FRIENDS", url=self.config.share_link)],
                [InlineKeyboardButton("✅ Step 3: CHECK STATUS", callback_data="status")],
                [InlineKeyboardButton("❓ HELP & INFO", callback_data="help")]
            ]
            
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            try:
                await update.message.reply_text(
                    "⚠️ Error loading bot. Please try again with /start",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
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
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 5))
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            try:
                await update.message.reply_text(
                    "⚠️ Error checking status. Please try again.",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        try:
            text = self.formatter.help_message()
            
            keyboard = [[InlineKeyboardButton("🏠 Back to Start", callback_data="back_to_start")]]
            
            msg = await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 5))
            
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            try:
                await update.message.reply_text(
                    "⚠️ Error loading help. Please try again.",
                    parse_mode="Markdown"
                )
            except:
                pass


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
        try:
            query = update.callback_query
            user = query.from_user
            username = user.username or user.first_name or "User"
            
            # Answer callback to remove loading state
            await query.answer()
            
            data = query.data
            
            if data == "status":
                await self._handle_status(query, user, username)
            elif data == "help":
                await self._handle_help(query)
            elif data == "back_to_start":
                await self._handle_back_to_start(query, username)
            else:
                await query.edit_message_text(
                    "❌ Unknown action. Please use /start to restart.",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error in callback handler: {e}")
            try:
                await query.answer("⚠️ Error occurred. Please try again.", show_alert=True)
            except:
                pass
    
    async def _handle_status(self, query, user, username):
        """Handle status callback"""
        try:
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
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error in status handler: {e}")
            await query.edit_message_text(
                "❌ Error loading status. Please try /status command.",
                parse_mode="Markdown"
            )
    
    async def _handle_help(self, query):
        """Handle help callback"""
        try:
            text = self.formatter.help_message()
            
            keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error in help handler: {e}")
            await query.edit_message_text(
                "❌ Error loading help. Please use /help command.",
                parse_mode="Markdown"
            )
    
    async def _handle_back_to_start(self, query, username):
        """Handle back to start callback"""
        try:
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
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error in back_to_start handler: {e}")
            await query.edit_message_text(
                "❌ Error loading main menu. Please use /start command.",
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
        try:
            if not self.is_admin(update.effective_user.id):
                msg = await update.message.reply_text(
                    "🚫 **Access Denied:** Admin only command.",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                return
            
            args = context.args
            if not args:
                msg = await update.message.reply_text(
                    "📋 **Usage:** `/approve <telegram_id> [days]`\n\n"
                    "**Examples:**\n"
                    "• `/approve 123456789` → 30 days default\n"
                    "• `/approve 123456789 60` → 60 days custom\n\n"
                    "💡 _Tip: Forward a message from the user to get their ID_",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 5))
                return
            
            try:
                telegram_id = int(args[0])
                days = int(args[1]) if len(args) > 1 else self.config.default_vip_days
                
                if days <= 0:
                    raise ValueError("Days must be greater than 0")
                
                if days > 365:
                    raise ValueError("Days cannot exceed 365")
                
                until_date = self.db.approve_user(telegram_id, days)
                
                msg = await update.message.reply_text(
                    f"✅ **User Approved Successfully!**\n\n"
                    f"👤 User ID: `{telegram_id}`\n"
                    f"📅 VIP Days: **{days} days**\n"
                    f"⏰ Valid Until: **{until_date}**",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 5))
                
                # Notify user
                try:
                    await context.bot.send_message(
                        telegram_id,
                        f"🎉 **Congratulations!**\n\n"
                        f"✅ Na-approve ka na para sa **{days} days VIP Access!**\n\n"
                        f"💎 **Access your VIP content here:**\n"
                        f"👉 {self.config.vip_channel_link}\n\n"
                        f"📅 Valid until: **{until_date}**\n\n"
                        f"Salamat at enjoy! 🎊",
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
                    logger.info(f"✅ Notified user {telegram_id} of approval")
                except TelegramError as e:
                    logger.error(f"❌ Could not notify user {telegram_id}: {e}")
                    await update.message.reply_text(
                        f"⚠️ **User approved** pero hindi ma-notify:\n`{e}`",
                        parse_mode="Markdown"
                    )
            
            except ValueError as e:
                msg = await update.message.reply_text(
                    f"❌ **Invalid input:** {e}\n\n"
                    f"Usage: `/approve <telegram_id> [days]`",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
        
        except Exception as e:
            logger.error(f"Error in approve command: {e}")
            try:
                msg = await update.message.reply_text(
                    f"⚠️ **Unexpected error:** {e}",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            except:
                pass
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        try:
            if not self.is_admin(update.effective_user.id):
                msg = await update.message.reply_text(
                    "🚫 **Access Denied:** Admin only command.",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                return
            
            total_users = self.db.get_total_users()
            vip_users = self.db.get_vip_users_count()
            regular_users = total_users - vip_users
            conversion_rate = (vip_users / total_users * 100) if total_users > 0 else 0
            
            text = (
                "📊 **Bot Statistics**\n\n"
                f"👥 Total Users: **{total_users:,}**\n"
                f"💎 Active VIP Users: **{vip_users:,}**\n"
                f"👤 Regular Users: **{regular_users:,}**\n\n"
                f"📈 VIP Conversion Rate: **{conversion_rate:.1f}%**\n\n"
                f"_Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
            )
            
            keyboard = [[InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_stats")]]
            
            msg = await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 10))
            
        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            try:
                await update.message.reply_text(
                    f"⚠️ Error loading stats: {e}",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users"""
        try:
            if not self.is_admin(update.effective_user.id):
                msg = await update.message.reply_text(
                    "🚫 **Access Denied:** Admin only command.",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                return
            
            if not context.args:
                msg = await update.message.reply_text(
                    "📋 **Usage:** `/broadcast <message>`\n\n"
                    "**Example:**\n"
                    "`/broadcast Happy New Year to all VIP members!`\n\n"
                    "⚠️ _This will send the message to ALL users_",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                return
            
            announcement = " ".join(context.args)
            user_ids = self.db.get_all_user_ids()
            
            if not user_ids:
                await update.message.reply_text(
                    "❌ No users found in database.",
                    parse_mode="Markdown"
                )
                return
            
            status_msg = await update.message.reply_text(
                f"📡 **Broadcasting...**\n\n"
                f"Total recipients: **{len(user_ids):,}**\n"
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
                    
                    # Rate limiting
                    if sent_count % 20 == 0:  # Update progress every 20 messages
                        try:
                            await status_msg.edit_text(
                                f"📡 **Broadcasting...**\n\n"
                                f"Progress: **{sent_count}/{len(user_ids)}**\n"
                                f"_Please wait..._",
                                parse_mode="Markdown"
                            )
                        except:
                            pass
                    
                    await asyncio.sleep(self.config.broadcast_delay)
                    
                except TelegramError as e:
                    logger.debug(f"Failed to send to {user_id}: {e}")
                    failed_count += 1
                except Exception as e:
                    logger.error(f"Unexpected error sending to {user_id}: {e}")
                    failed_count += 1
            
            success_rate = (sent_count / (sent_count + failed_count) * 100) if (sent_count + failed_count) > 0 else 0
            
            await status_msg.edit_text(
                f"✅ **Broadcast Complete!**\n\n"
                f"📬 Successfully sent: **{sent_count:,}**\n"
                f"❌ Failed: **{failed_count:,}**\n"
                f"📊 Success rate: **{success_rate:.1f}%**",
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete_message(status_msg, self.config.delete_after + 10))
            
        except Exception as e:
            logger.error(f"Error in broadcast command: {e}")
            try:
                await update.message.reply_text(
                    f"⚠️ Broadcast error: {e}",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    async def pin_announcement(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pin an announcement in the chat"""
        try:
            if not self.is_admin(update.effective_user.id):
                msg = await update.message.reply_text(
                    "🚫 **Access Denied:** Admin only command.",
                    parse_mode="Markdown"
                )
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
                logger.info(f"✅ Pinned announcement by admin {update.effective_user.id}")
            except TelegramError as e:
                logger.error(f"Could not pin message: {e}")
                error_msg = await update.message.reply_text(
                    f"⚠️ **Error pinning message:** {e}",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(error_msg, self.config.delete_after))
                
        except Exception as e:
            logger.error(f"Error in pin command: {e}")
            try:
                await update.message.reply_text(
                    f"⚠️ Error: {e}",
                    parse_mode="Markdown"
                )
            except:
                pass


# =========================
# ERROR HANDLER
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ **Oops! Something went wrong.**\n\n"
                "Please try again later or contact support.\n\n"
                "💬 Support: @PinayWalkerManilaBot",
                parse_mode="Markdown"
            )
        except TelegramError:
            pass
        except Exception:
            pass


# =========================
# MAIN APPLICATION
# =========================
def main():
    """Initialize and run the bot"""
    try:
        print("=" * 50)
        print("🤖 VIP Access Bot Starting...")
        print("=" * 50)
        
        # Load configuration
        config = load_config()
        logger.info("✅ Configuration loaded successfully")
        logger.info(f"👤 Admin ID: {config.admin_telegram_id}")
        
        # Initialize database
        db = DatabaseManager(config.db_path)
        logger.info(f"✅ Database initialized at: {config.db_path}")
        
        # Initialize handlers
        user_handlers = UserHandlers(db, config)
        admin_handlers = AdminHandlers(db, config)
        callback_handler = CallbackHandler(db, config)
        
        logger.info("✅ Handlers initialized successfully")
        
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
        
        logger.info("✅ All handlers registered successfully")
        print("\n" + "=" * 50)
        print("🚀 Bot is now LIVE and running!")
        print("=" * 50)
        print("\n💡 Commands:")
        print("  • User: /start, /status, /help")
        print("  • Admin: /approve, /stats, /broadcast, /pin")
        print("\n⌨️  Press Ctrl+C to stop the bot")
        print("=" * 50 + "\n")
        
        # Start polling
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"❌ Failed to start bot: {e}", exc_info=True)
        print(f"\n❌ CRITICAL ERROR: {e}")
        print("Please check bot.log for details")
        raise


if __name__ == "__main__":
    main()
