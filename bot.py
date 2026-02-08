"""
VIP Access Telegram Bot
A professional bot with referral system and pay-to-enter mechanics.
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
    MessageHandler,
    ContextTypes,
    filters,
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
    pay_link: str = "https://tinyurl.com/PinayAtbsPay"
    share_link: str = "https://telegram.me/share/url?url=https%3A%2F%2Ft.me%2Fpinaygroupchatbot&start=LIBRE%20ATABS%20LEAKS%20DITO%20🤪🤪"
    vip_channel_link: str = "https://t.me/+MMRjUFZqsmpmN2Vl"
    welcome_image: str = "welcome.jpg"
    db_path: str = "vip.db"
    delete_after: int = 9999
    default_vip_days: int = 30
    broadcast_delay: float = 0.5
    entrance_fee: int = 305
    referral_target: int = 500  # Number of referrals needed for free access


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
                        last_activity TEXT DEFAULT CURRENT_TIMESTAMP,
                        referral_code TEXT UNIQUE,
                        referred_by INTEGER,
                        referral_count INTEGER DEFAULT 0,
                        FOREIGN KEY (referred_by) REFERENCES users(telegram_id)
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
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER,
                        username TEXT,
                        first_name TEXT,
                        message TEXT,
                        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                        replied INTEGER DEFAULT 0,
                        FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
                    )
                """)
                
                conn.commit()
            logger.info("✅ Database initialized successfully")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    def generate_referral_code(self, telegram_id: int) -> str:
        """Generate unique referral code for user"""
        return f"REF{telegram_id}"
    
    def add_or_update_user(self, telegram_id: int, username: str, first_name: str, referred_by_code: Optional[str] = None) -> Optional[Dict]:
        """Add new user or update existing user information. Returns referrer info if this is a new referral."""
        try:
            with self.get_connection() as conn:
                # Check if user exists
                existing = conn.execute(
                    "SELECT telegram_id, referred_by FROM users WHERE telegram_id = ?",
                    (telegram_id,)
                ).fetchone()
                
                if existing:
                    # Update existing user
                    conn.execute("""
                        UPDATE users SET
                            username = ?,
                            first_name = ?,
                            last_activity = ?
                        WHERE telegram_id = ?
                    """, (username, first_name, datetime.utcnow().isoformat(), telegram_id))
                    conn.commit()
                    return None
                else:
                    # New user
                    referral_code = self.generate_referral_code(telegram_id)
                    referred_by_id = None
                    referrer_info = None
                    
                    # Process referral code if provided
                    if referred_by_code:
                        referrer = conn.execute(
                            "SELECT telegram_id, first_name, referral_count FROM users WHERE referral_code = ?",
                            (referred_by_code,)
                        ).fetchone()
                        
                        if referrer:
                            referred_by_id = referrer["telegram_id"]
                            # Increment referrer's count
                            new_count = referrer["referral_count"] + 1
                            conn.execute(
                                "UPDATE users SET referral_count = ? WHERE telegram_id = ?",
                                (new_count, referred_by_id)
                            )
                            logger.info(f"User {telegram_id} referred by {referred_by_id}")
                            
                            # Prepare referrer info for notification
                            referrer_info = {
                                'telegram_id': referred_by_id,
                                'first_name': referrer["first_name"],
                                'new_user_name': first_name,
                                'new_count': new_count
                            }
                    
                    conn.execute("""
                        INSERT INTO users (telegram_id, username, first_name, last_activity, referral_code, referred_by)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (telegram_id, username, first_name, datetime.utcnow().isoformat(), referral_code, referred_by_id))
                    
                    conn.commit()
                    return referrer_info
        except Exception as e:
            logger.error(f"Error adding/updating user {telegram_id}: {e}")
            return None
    
    def get_user(self, telegram_id: int) -> Dict:
        """Get user information"""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    "SELECT paid, shared, vip_until, referral_code, referral_count, referred_by FROM users WHERE telegram_id = ?",
                    (telegram_id,)
                ).fetchone()
                
                if not row:
                    return {
                        "paid": False,
                        "shared": False,
                        "vip_until": None,
                        "referral_code": None,
                        "referral_count": 0,
                        "referred_by": None
                    }
                
                return {
                    "paid": bool(row["paid"]),
                    "shared": bool(row["shared"]),
                    "vip_until": row["vip_until"],
                    "referral_code": row["referral_code"],
                    "referral_count": row["referral_count"],
                    "referred_by": row["referred_by"]
                }
        except Exception as e:
            logger.error(f"Error getting user {telegram_id}: {e}")
            return {
                "paid": False,
                "shared": False,
                "vip_until": None,
                "referral_code": None,
                "referral_count": 0,
                "referred_by": None
            }
    
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
    
    def save_user_message(self, telegram_id: int, username: str, first_name: str, message: str):
        """Save user message for admin"""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT INTO user_messages (telegram_id, username, first_name, message)
                    VALUES (?, ?, ?, ?)
                """, (telegram_id, username, first_name, message))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving message from {telegram_id}: {e}")
    
    def get_user_messages(self, limit: int = 20) -> List[Dict]:
        """Get recent user messages"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute("""
                    SELECT id, telegram_id, username, first_name, message, timestamp, replied
                    FROM user_messages
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                
                return [{
                    "id": row["id"],
                    "telegram_id": row["telegram_id"],
                    "username": row["username"],
                    "first_name": row["first_name"],
                    "message": row["message"],
                    "timestamp": row["timestamp"],
                    "replied": bool(row["replied"])
                } for row in rows]
        except Exception as e:
            logger.error(f"Error getting user messages: {e}")
            return []
    
    def mark_message_replied(self, message_id: int):
        """Mark message as replied"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE user_messages SET replied = 1 WHERE id = ?",
                    (message_id,)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Error marking message {message_id} as replied: {e}")
    
    def check_and_approve_referrals(self, config: BotConfig) -> List[Dict]:
        """Check users who reached referral target and return them for approval"""
        try:
            with self.get_connection() as conn:
                users = conn.execute("""
                    SELECT telegram_id, referral_count, first_name
                    FROM users
                    WHERE referral_count >= ?
                    AND (vip_until IS NULL OR vip_until < ?)
                """, (config.referral_target, datetime.utcnow().isoformat())).fetchall()
                
                return [{
                    "telegram_id": row["telegram_id"],
                    "referral_count": row["referral_count"],
                    "first_name": row["first_name"]
                } for row in users]
        except Exception as e:
            logger.error(f"Error checking referrals: {e}")
            return []


# =========================
# MESSAGE UTILITIES
# =========================
class MessageFormatter:
    """Format messages with consistent styling"""
    
    @staticmethod
    def welcome_message(username: str, vip_link: str, entrance_fee: int, referral_target: int, bot_username: str, referral_code: str) -> str:
        """Format welcome message"""
        return (
            f"👋 Kumusta, **{username}!**\n\n"
            f"🎁 **Dalawang Paraan Para Makakuha ng 30 Days VIP Access:**\n\n"
            f"**OPTION 1: Mag-bayad ng ₱{entrance_fee}** 💰\n"
            "• I-click ang 'PAY ₱305' button\n"
            "• I-share sa 3 friends\n"
            "• Instant approval pagkatapos ng payment!\n\n"
            f"**OPTION 2: LIBRE! Mag-refer ng {referral_target} users** 🎯\n"
            f"• Walang bayad, refer lang!\n"
            f"• I-share ang iyong referral link\n"
            f"• Pag naka-{referral_target} referrals, FREE VIP access!\n\n"
            "💎 **VIP Benefits:**\n"
            f"• Access sa VIP Channel: {vip_link}\n"
            "• 10,000+ exclusive premium leaks\n"
            "• Premium photos at videos\n"
            "• 30 days ng VIP access!\n\n"
            f"📊 **Your Referral Progress:**\n"
            f"🔗 Referral Link: `https://t.me/{bot_username}?start={referral_code}`\n"
            f"👥 Referrals: Loading...\n\n"
            "👇 Pumili ng option mo:"
        )
    
    @staticmethod
    def status_message(username: str, paid: bool, shared: bool, vip_until: Optional[str], vip_link: str, 
                       entrance_fee: int, referral_count: int, referral_target: int, referral_code: str, bot_username: str) -> str:
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
        
        # Calculate referral progress
        referral_progress = (referral_count / referral_target) * 100
        remaining = referral_target - referral_count
        
        return (
            f"📊 **Status ni {username}**\n\n"
            f"💰 Payment (₱{entrance_fee}): {'✅ Complete' if paid else '❌ Pending'}\n"
            f"📤 Sharing: {'✅ Complete' if shared else '❌ Pending'}\n"
            f"💎 VIP Access: {vip_status}\n\n"
            f"🎯 **Referral Status:**\n"
            f"👥 Current Referrals: **{referral_count}/{referral_target}**\n"
            f"📈 Progress: **{referral_progress:.1f}%**\n"
            f"🎁 Remaining: **{remaining}** more for FREE VIP!\n\n"
            f"🔗 **Your Referral Link:**\n"
            f"`https://t.me/{bot_username}?start={referral_code}`\n\n"
            f"📱 **VIP Channel:** {vip_link}\n\n"
            "💬 _Para mag-message sa admin, i-type lang ang message mo dito!_"
        )
    
    @staticmethod
    def help_message(entrance_fee: int, referral_target: int) -> str:
        """Format help message"""
        return (
            "📖 **Available Commands**\n\n"
            "**Para sa lahat:**\n"
            "• `/start` - Simulan ang bot\n"
            "• `/status` - Tingnan ang iyong status\n"
            "• `/referrals` - Tingnan referral stats\n"
            "• `/help` - Tingnan ang help menu\n\n"
            "**2 Ways to Get VIP Access:**\n\n"
            f"**💰 INSTANT: Pay ₱{entrance_fee}**\n"
            f"1️⃣ Magbayad ng ₱{entrance_fee}\n"
            "2️⃣ I-share sa 3 friends\n"
            "3️⃣ Message @PinayWalkerManilaBot with proof\n"
            "4️⃣ Instant approval!\n\n"
            f"**🎯 INVITE: Refer {referral_target} Users (FREE!)**\n"
            "1️⃣ Get your referral link from /status\n"
            f"2️⃣ Share at mag-invite ng {referral_target} users\n"
            f"3️⃣ Pag {referral_target} na, auto-approved ka!\n\n"
            "**Payment Methods:**\n"
            "💳 GCash • Maya • Bank Transfer\n\n"
            "**📩 Contact Admin:**\n"
            "I-type lang ang message mo sa chat, automatic forward sa admin!\n\n"
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
# USER COMMAND HANDLERS
# =========================
class UserHandlers:
    """Handlers for user commands"""
    
    def __init__(self, db: DatabaseManager, config: BotConfig, bot_username: str):
        self.db = db
        self.config = config
        self.formatter = MessageFormatter()
        self.bot_username = bot_username
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        try:
            user = update.effective_user
            username = user.username or user.first_name or "User"
            
            # Check for referral code
            referred_by_code = None
            if context.args:
                referred_by_code = context.args[0]
                logger.info(f"User {user.id} started with referral code: {referred_by_code}")
            
            # Update user in database and get referrer info if this is a new referral
            referrer_info = self.db.add_or_update_user(user.id, user.username or "", user.first_name or "User", referred_by_code)
            logger.info(f"User {user.id} ({username}) started the bot")
            
            # If this was a new referral, notify the referrer
            if referrer_info:
                try:
                    await context.bot.send_message(
                        chat_id=referrer_info['telegram_id'],
                        text=(
                            f"🎉 **New Referral!**\n\n"
                            f"✅ **{referrer_info['new_user_name']}** just joined using your link!\n\n"
                            f"👥 Total Referrals: **{referrer_info['new_count']}/{self.config.referral_target}**\n"
                            f"🎁 Only **{self.config.referral_target - referrer_info['new_count']}** more for FREE VIP!\n\n"
                            f"Keep sharing! 🚀"
                        ),
                        parse_mode="Markdown"
                    )
                    logger.info(f"Notified user {referrer_info['telegram_id']} of new referral")
                except Exception as e:
                    logger.error(f"Could not notify referrer {referrer_info['telegram_id']}: {e}")
            
            # Check if user reached referral target
            await self._check_referral_approval(update, context)
            
            # Get user data for referral info
            user_data = self.db.get_user(user.id)
            
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
            text = self.formatter.welcome_message(
                username, 
                self.config.vip_channel_link, 
                self.config.entrance_fee,
                self.config.referral_target,
                self.bot_username,
                user_data["referral_code"]
            )
            
            keyboard = [
                [InlineKeyboardButton(f"💰 OPTION 1: PAY ₱{self.config.entrance_fee}", url=self.config.pay_link)],
                [InlineKeyboardButton(f"🎯 OPTION 2: GET YOUR REFERRAL LINK", callback_data="get_referral")],
                [InlineKeyboardButton("✅ CHECK STATUS", callback_data="status")],
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
    
    async def _check_referral_approval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check and auto-approve users who reached referral target"""
        try:
            users_to_approve = self.db.check_and_approve_referrals(self.config)
            
            for user_info in users_to_approve:
                telegram_id = user_info["telegram_id"]
                
                # Only approve the current user if they're in the list
                if telegram_id == update.effective_user.id:
                    try:
                        until_date = self.db.approve_user(telegram_id, self.config.default_vip_days)
                        
                        # Notify user
                        await update.message.reply_text(
                            f"🎉🎉🎉 **CONGRATULATIONS {user_info['first_name']}!** 🎉🎉🎉\n\n"
                            f"✅ Naka-{self.config.referral_target} referrals ka na!\n\n"
                            f"💎 **FREE 30 Days VIP Access activated!**\n\n"
                            f"🔗 **Access your VIP channel:**\n"
                            f"👉 {self.config.vip_channel_link}\n\n"
                            f"📅 Valid until: **{until_date}**\n\n"
                            f"Salamat sa pagsupport! Enjoy your FREE VIP access! 🎊",
                            parse_mode="Markdown",
                            disable_web_page_preview=True
                        )
                        
                        logger.info(f"✅ Auto-approved user {telegram_id} via referrals")
                        
                    except Exception as e:
                        logger.error(f"Error auto-approving user {telegram_id}: {e}")
                        
        except Exception as e:
            logger.error(f"Error in referral check: {e}")
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            user = update.effective_user
            username = user.username or user.first_name or "User"
            
            # Check referral approval first
            await self._check_referral_approval(update, context)
            
            user_data = self.db.get_user(user.id)
            text = self.formatter.status_message(
                username,
                user_data["paid"],
                user_data["shared"],
                user_data["vip_until"],
                self.config.vip_channel_link,
                self.config.entrance_fee,
                user_data["referral_count"],
                self.config.referral_target,
                user_data["referral_code"],
                self.bot_username
            )
            
            keyboard = [
                [InlineKeyboardButton("🔗 Share Referral Link", callback_data="share_referral")],
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
    
    async def referrals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /referrals command"""
        try:
            user = update.effective_user
            
            # Check referral approval first
            await self._check_referral_approval(update, context)
            
            user_data = self.db.get_user(user.id)
            
            referral_count = user_data["referral_count"]
            referral_code = user_data["referral_code"]
            remaining = self.config.referral_target - referral_count
            progress = (referral_count / self.config.referral_target) * 100
            
            text = (
                f"🎯 **Your Referral Stats**\n\n"
                f"👥 Total Referrals: **{referral_count}/{self.config.referral_target}**\n"
                f"📈 Progress: **{progress:.1f}%**\n"
                f"🎁 Remaining: **{remaining}** more for FREE VIP!\n\n"
                f"🔗 **Your Unique Referral Link:**\n"
                f"`https://t.me/{self.bot_username}?start={referral_code}`\n\n"
                f"💡 **How it works:**\n"
                f"1. Share your link sa mga kaibigan\n"
                f"2. Kada user na gumamit ng link mo = +1 referral\n"
                f"3. Pag naka-{self.config.referral_target} ka, FREE 30 days VIP!\n\n"
                f"📤 Share now and start earning!"
            )
            
            keyboard = [
                [InlineKeyboardButton("📤 Share My Link", callback_data="share_referral")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="referrals")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]
            ]
            
            msg = await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 5))
            
        except Exception as e:
            logger.error(f"Error in referrals command: {e}")
            try:
                await update.message.reply_text(
                    "⚠️ Error loading referral stats. Please try again.",
                    parse_mode="Markdown"
                )
            except:
                pass
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        try:
            text = self.formatter.help_message(self.config.entrance_fee, self.config.referral_target)
            
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
    
    async def handle_user_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages from users and forward to admin"""
        try:
            user = update.effective_user
            message_text = update.message.text
            
            # Don't process commands
            if message_text.startswith('/'):
                return
            
            # Save message to database
            self.db.save_user_message(
                user.id,
                user.username or "",
                user.first_name or "User",
                message_text
            )
            
            # Forward to admin
            try:
                admin_msg = (
                    f"📩 **New Message from User**\n\n"
                    f"👤 Name: {user.first_name or 'N/A'}\n"
                    f"🆔 Username: @{user.username or 'N/A'}\n"
                    f"🔢 ID: `{user.id}`\n\n"
                    f"💬 Message:\n{message_text}\n\n"
                    f"_Reply using: /reply {user.id} <your message>_"
                )
                
                await context.bot.send_message(
                    chat_id=self.config.admin_telegram_id,
                    text=admin_msg,
                    parse_mode="Markdown"
                )
                
                # Confirm to user
                confirmation = await update.message.reply_text(
                    "✅ **Message sent to admin!**\n\n"
                    "Maghintay lang ng reply. Thank you! 😊",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(confirmation, 30))
                
                logger.info(f"Forwarded message from user {user.id} to admin")
                
            except Exception as e:
                logger.error(f"Error forwarding message to admin: {e}")
                error_msg = await update.message.reply_text(
                    "⚠️ Error sending message to admin. Please try again later.",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(error_msg, 10))
                
        except Exception as e:
            logger.error(f"Error handling user message: {e}")


# =========================
# CALLBACK QUERY HANDLER
# =========================
class CallbackHandler:
    """Handle callback queries from inline buttons"""
    
    def __init__(self, db: DatabaseManager, config: BotConfig, bot_username: str):
        self.db = db
        self.config = config
        self.formatter = MessageFormatter()
        self.bot_username = bot_username
    
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
            elif data == "get_referral":
                await self._handle_get_referral(query, user)
            elif data == "share_referral":
                await self._handle_share_referral(query, user)
            elif data == "referrals":
                await self._handle_referrals_callback(query, user)
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
                self.config.vip_channel_link,
                self.config.entrance_fee,
                user_data["referral_count"],
                self.config.referral_target,
                user_data["referral_code"],
                self.bot_username
            )
            
            keyboard = [
                [InlineKeyboardButton("🔗 Share Referral Link", callback_data="share_referral")],
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
            text = self.formatter.help_message(self.config.entrance_fee, self.config.referral_target)
            
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
            user_data = self.db.get_user(query.from_user.id)
            text = self.formatter.welcome_message(
                username, 
                self.config.vip_channel_link, 
                self.config.entrance_fee,
                self.config.referral_target,
                self.bot_username,
                user_data["referral_code"]
            )
            
            keyboard = [
                [InlineKeyboardButton(f"💰 OPTION 1: PAY ₱{self.config.entrance_fee}", url=self.config.pay_link)],
                [InlineKeyboardButton(f"🎯 OPTION 2: GET YOUR REFERRAL LINK", callback_data="get_referral")],
                [InlineKeyboardButton("✅ CHECK STATUS", callback_data="status")],
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
    
    async def _handle_get_referral(self, query, user):
        """Handle get referral link callback"""
        try:
            user_data = self.db.get_user(user.id)
            referral_link = f"https://t.me/{self.bot_username}?start={user_data['referral_code']}"
            
            text = (
                f"🎯 **Your Referral Link**\n\n"
                f"🔗 **Link:**\n`{referral_link}`\n\n"
                f"👥 Current Referrals: **{user_data['referral_count']}/{self.config.referral_target}**\n\n"
                f"💡 **I-share ang link mo para:**\n"
                f"• Pag {self.config.referral_target} referrals = FREE VIP!\n"
                f"• Share sa social media, groups, friends\n"
                f"• Copy at i-paste kahit saan!\n\n"
                f"📤 Click 'Share Now' para i-share!"
            )
            
            share_text = f"🎁 Join VIP Access Bot! {referral_link}"
            share_url = f"https://telegram.me/share/url?url={referral_link}&text=🎁%20Join%20VIP%20Access%20Bot!"
            
            keyboard = [
                [InlineKeyboardButton("📤 Share Now", url=share_url)],
                [InlineKeyboardButton("📊 View Stats", callback_data="referrals")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]
            ]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error in get_referral handler: {e}")
            await query.answer("⚠️ Error getting referral link.", show_alert=True)
    
    async def _handle_share_referral(self, query, user):
        """Handle share referral callback"""
        try:
            user_data = self.db.get_user(user.id)
            referral_link = f"https://t.me/{self.bot_username}?start={user_data['referral_code']}"
            share_url = f"https://telegram.me/share/url?url={referral_link}&text=🎁%20Join%20VIP%20Access%20Bot!"
            
            # Open share dialog
            await query.answer(url=share_url)
        except Exception as e:
            logger.error(f"Error in share_referral handler: {e}")
            await query.answer("⚠️ Error sharing link.", show_alert=True)
    
    async def _handle_referrals_callback(self, query, user):
        """Handle referrals stats callback"""
        try:
            user_data = self.db.get_user(user.id)
            
            referral_count = user_data["referral_count"]
            referral_code = user_data["referral_code"]
            remaining = self.config.referral_target - referral_count
            progress = (referral_count / self.config.referral_target) * 100
            
            text = (
                f"🎯 **Your Referral Stats**\n\n"
                f"👥 Total Referrals: **{referral_count}/{self.config.referral_target}**\n"
                f"📈 Progress: **{progress:.1f}%**\n"
                f"🎁 Remaining: **{remaining}** more for FREE VIP!\n\n"
                f"🔗 **Your Unique Referral Link:**\n"
                f"`https://t.me/{self.bot_username}?start={referral_code}`\n\n"
                f"💡 **How it works:**\n"
                f"1. Share your link sa mga kaibigan\n"
                f"2. Kada user na gumamit ng link mo = +1 referral\n"
                f"3. Pag naka-{self.config.referral_target} ka, FREE 30 days VIP!\n\n"
                f"📤 Share now and start earning!"
            )
            
            keyboard = [
                [InlineKeyboardButton("📤 Share My Link", callback_data="share_referral")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="referrals")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]
            ]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Error in referrals callback: {e}")
            await query.answer("⚠️ Error loading stats.", show_alert=True)


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
        """Approve user for VIP access (admin only)"""
        try:
            if not self.is_admin(update.effective_user.id):
                return  # Silently ignore for non-admins
            
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
                        f"Salamat at enjoy your VIP access! 🎊",
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
            if self.is_admin(update.effective_user.id):
                try:
                    msg = await update.message.reply_text(
                        f"⚠️ **Unexpected error:** {e}",
                        parse_mode="Markdown"
                    )
                    asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                except:
                    pass
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics (admin only)"""
        try:
            if not self.is_admin(update.effective_user.id):
                return  # Silently ignore for non-admins
            
            total_users = self.db.get_total_users()
            vip_users = self.db.get_vip_users_count()
            regular_users = total_users - vip_users
            conversion_rate = (vip_users / total_users * 100) if total_users > 0 else 0
            total_revenue = vip_users * self.config.entrance_fee
            
            text = (
                "📊 **Bot Statistics**\n\n"
                f"👥 Total Users: **{total_users:,}**\n"
                f"💎 Active VIP Users: **{vip_users:,}**\n"
                f"👤 Regular Users: **{regular_users:,}**\n\n"
                f"📈 VIP Conversion Rate: **{conversion_rate:.1f}%**\n"
                f"💰 Total Revenue: **₱{total_revenue:,}**\n\n"
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
            if self.is_admin(update.effective_user.id):
                try:
                    await update.message.reply_text(
                        f"⚠️ Error loading stats: {e}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    
    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message to all users (admin only)"""
        try:
            if not self.is_admin(update.effective_user.id):
                return  # Silently ignore for non-admins
            
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
                    if sent_count % 20 == 0:
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
            if self.is_admin(update.effective_user.id):
                try:
                    await update.message.reply_text(
                        f"⚠️ Broadcast error: {e}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    
    async def pin_announcement(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pin an announcement in the chat (admin only)"""
        try:
            if not self.is_admin(update.effective_user.id):
                return  # Silently ignore for non-admins
            
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
            if self.is_admin(update.effective_user.id):
                try:
                    await update.message.reply_text(
                        f"⚠️ Error: {e}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    
    async def reply_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reply to user message (admin only)"""
        try:
            if not self.is_admin(update.effective_user.id):
                return  # Silently ignore for non-admins
            
            if len(context.args) < 2:
                msg = await update.message.reply_text(
                    "📋 **Usage:** `/reply <user_id> <message>`\n\n"
                    "**Example:**\n"
                    "`/reply 123456789 Thank you for your payment!`",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                return
            
            try:
                user_id = int(context.args[0])
                reply_text = " ".join(context.args[1:])
                
                # Send reply to user
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"📩 **Reply from Admin:**\n\n{reply_text}",
                    parse_mode="Markdown"
                )
                
                # Confirm to admin
                msg = await update.message.reply_text(
                    f"✅ **Reply sent to user {user_id}**",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                
                logger.info(f"Admin replied to user {user_id}")
                
            except ValueError:
                msg = await update.message.reply_text(
                    "❌ Invalid user ID. Please use a valid number.",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
            except TelegramError as e:
                logger.error(f"Error sending reply to user {user_id}: {e}")
                msg = await update.message.reply_text(
                    f"⚠️ **Error sending reply:** {e}",
                    parse_mode="Markdown"
                )
                asyncio.create_task(auto_delete_message(msg, self.config.delete_after))
                
        except Exception as e:
            logger.error(f"Error in reply command: {e}")
            if self.is_admin(update.effective_user.id):
                try:
                    await update.message.reply_text(
                        f"⚠️ Error: {e}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    
    async def messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View recent user messages (admin only)"""
        try:
            if not self.is_admin(update.effective_user.id):
                return  # Silently ignore for non-admins
            
            messages = self.db.get_user_messages(20)
            
            if not messages:
                await update.message.reply_text(
                    "📭 No messages yet.",
                    parse_mode="Markdown"
                )
                return
            
            text = "📩 **Recent User Messages:**\n\n"
            
            for msg in messages[:10]:  # Show last 10
                status = "✅" if msg["replied"] else "❌"
                timestamp = datetime.fromisoformat(msg["timestamp"]).strftime("%m/%d %H:%M")
                text += (
                    f"{status} **{msg['first_name']}** (@{msg['username'] or 'N/A'})\n"
                    f"🔢 ID: `{msg['telegram_id']}`\n"
                    f"💬 {msg['message'][:50]}{'...' if len(msg['message']) > 50 else ''}\n"
                    f"🕐 {timestamp}\n\n"
                )
            
            text += f"_Showing {min(10, len(messages))} of {len(messages)} messages_"
            
            msg = await update.message.reply_text(
                text,
                parse_mode="Markdown"
            )
            asyncio.create_task(auto_delete_message(msg, self.config.delete_after + 10))
            
        except Exception as e:
            logger.error(f"Error in messages command: {e}")
            if self.is_admin(update.effective_user.id):
                try:
                    await update.message.reply_text(
                        f"⚠️ Error loading messages: {e}",
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
async def setup_and_run():
    """Async setup and run function"""
    # Load configuration
    config = load_config()
    logger.info("✅ Configuration loaded successfully")
    logger.info(f"👤 Admin ID: {config.admin_telegram_id}")
    logger.info(f"💰 Entrance Fee: ₱{config.entrance_fee}")
    logger.info(f"🎯 Referral Target: {config.referral_target}")
    
    # Initialize database
    db = DatabaseManager(config.db_path)
    logger.info(f"✅ Database initialized at: {config.db_path}")
    
    # Build application
    app = Application.builder().token(config.bot_token).build()
    
    # Get bot username
    bot_username = (await app.bot.get_me()).username
    logger.info(f"🤖 Bot Username: @{bot_username}")
    
    # Store in bot_data
    app.bot_data['db'] = db
    app.bot_data['config'] = config
    
    # Initialize handlers
    user_handlers = UserHandlers(db, config, bot_username)
    admin_handlers = AdminHandlers(db, config)
    callback_handler = CallbackHandler(db, config, bot_username)
    
    logger.info("✅ Handlers initialized successfully")
    
    # Add user command handlers
    app.add_handler(CommandHandler("start", user_handlers.start))
    app.add_handler(CommandHandler("status", user_handlers.status))
    app.add_handler(CommandHandler("referrals", user_handlers.referrals))
    app.add_handler(CommandHandler("help", user_handlers.help_command))
    
    # Add admin command handlers (hidden from normal users)
    app.add_handler(CommandHandler("approve", admin_handlers.approve))
    app.add_handler(CommandHandler("stats", admin_handlers.stats))
    app.add_handler(CommandHandler("broadcast", admin_handlers.broadcast))
    app.add_handler(CommandHandler("pin", admin_handlers.pin_announcement))
    app.add_handler(CommandHandler("reply", admin_handlers.reply_user))
    app.add_handler(CommandHandler("messages", admin_handlers.messages))
    
    # Add callback query handler
    app.add_handler(CallbackQueryHandler(callback_handler.handle))
    
    # Add message handler for user messages to admin
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        user_handlers.handle_user_message
    ))
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    logger.info("✅ All handlers registered successfully")
    print("\n" + "=" * 50)
    print("🚀 Bot is now LIVE and running!")
    print("=" * 50)
    print(f"\n💰 Pay to Enter: ₱{config.entrance_fee}")
    print(f"🎯 Referral Target: {config.referral_target} users = FREE VIP")
    print(f"🔗 Payment Link: {config.pay_link}")
    print("\n💡 User Commands:")
    print("  • /start, /status, /referrals, /help")
    print("\n🔐 Admin Commands (hidden):")
    print("  • /approve, /stats, /broadcast, /pin")
    print("  • /reply, /messages")
    print("\n📝 Note: Referral auto-approval checks on user actions")
    print("✨ New: Users get notified when someone uses their referral link!")
    print("\n⌨️  Press Ctrl+C to stop the bot")
    print("=" * 50 + "\n")
    
    # Start polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    """Initialize and run the bot"""
    try:
        print("=" * 50)
        print("🤖 VIP Access Bot Starting...")
        print("=" * 50)
        
        # Run the async setup
        asyncio.run(setup_and_run())
        
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
