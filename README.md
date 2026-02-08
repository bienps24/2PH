# 🤖 VIP Access Telegram Bot

A professional Telegram bot with **referral system** and **pay-to-enter mechanics**. Built with PostgreSQL for Railway deployment.

## ✨ Features

### 💰 Dual Access System
- **Option 1: Pay ₱305** - Instant VIP access after payment
- **Option 2: Refer 500 users** - FREE VIP access through referrals

### 🎯 Referral System
- ✅ Unique referral link for each user
- ✅ Real-time referral notifications
- ✅ Auto-approval when target is reached
- ✅ Progress tracking

### 💎 VIP Benefits
- 30 days VIP channel access
- 10,000+ premium content
- Exclusive photos and videos

### 🔧 Admin Features
- `/approve` - Approve users for VIP access
- `/stats` - View bot statistics
- `/broadcast` - Send announcements to all users
- `/reply` - Reply to user messages
- `/messages` - View recent user messages

### 📊 Database
- **PostgreSQL** - Persistent storage on Railway
- Connection pooling for performance
- Automatic table creation
- Indexed queries for speed

---

## 🚀 Railway Deployment

### Prerequisites
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Your Telegram ID (get from [@userinfobot](https://t.me/userinfobot))
- Railway account

### Step 1: Create PostgreSQL Database in Railway

1. Go to [Railway](https://railway.app)
2. Create new project
3. Click **"+ New"** → **"Database"** → **"Add PostgreSQL"**
4. Railway will automatically create `DATABASE_URL` variable

### Step 2: Deploy Bot

#### Option A: Deploy from GitHub (Recommended)

1. Push your code to GitHub:
   ```bash
   git add .
   git commit -m "Initial commit"
   git push origin main
   ```

2. In Railway:
   - Click **"+ New"** → **"GitHub Repo"**
   - Select your repository
   - Railway will auto-detect Python and deploy

#### Option B: Deploy with Railway CLI

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to project
railway link

# Deploy
railway up
```

### Step 3: Set Environment Variables

In Railway dashboard, go to your bot service → **Variables** tab:

```env
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_TELEGRAM_ID=123456789
DATABASE_URL=(automatically set by Railway PostgreSQL)
```

### Step 4: Verify Deployment

1. Check Railway logs for:
   ```
   ✅ PostgreSQL database connected
   🤖 Bot Username: @YourBot
   🚀 Bot is now LIVE and running!
   ```

2. Test bot:
   - Send `/start` to your bot
   - Check database connection
   - Verify referral system

---

## 📁 Project Structure

```
vip-access-bot/
├── bot.py                 # Main bot code (PostgreSQL version)
├── requirements.txt       # Python dependencies
├── Procfile              # Railway start command
├── runtime.txt           # Python version
├── .env.example          # Environment variables template
├── .gitignore            # Git ignore rules
├── README.md             # This file
└── assets/
    └── welcome.jpg       # Welcome image (optional)
```

---

## 🔧 Local Development

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/vip-access-bot.git
cd vip-access-bot
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Environment Variables
```bash
cp .env.example .env
# Edit .env with your values
```

### 4. Setup Local PostgreSQL (Optional)
```bash
# Install PostgreSQL
# Create database
createdb vip_bot

# Update .env
DATABASE_URL=postgresql://localhost/vip_bot
```

### 5. Run Bot
```bash
python bot.py
```

---

## 🗄️ Database Schema

### `users` Table
```sql
telegram_id BIGINT PRIMARY KEY
username TEXT
first_name TEXT
registered_at TIMESTAMP
paid BOOLEAN
shared BOOLEAN
vip_until TIMESTAMP
referral_code TEXT UNIQUE
referred_by BIGINT
referral_count INTEGER
```

### `activity_log` Table
```sql
id SERIAL PRIMARY KEY
telegram_id BIGINT
action TEXT
timestamp TIMESTAMP
```

### `user_messages` Table
```sql
id SERIAL PRIMARY KEY
telegram_id BIGINT
username TEXT
first_name TEXT
message TEXT
timestamp TIMESTAMP
replied BOOLEAN
```

---

## 🎮 User Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and see options |
| `/status` | Check VIP status and referrals |
| `/referrals` | View referral statistics |
| `/help` | Display help menu |

---

## 🔐 Admin Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/approve <id> [days]` | Approve user for VIP | `/approve 123456789 30` |
| `/stats` | View bot statistics | `/stats` |
| `/broadcast <msg>` | Send message to all users | `/broadcast Happy New Year!` |
| `/reply <id> <msg>` | Reply to user message | `/reply 123456789 Thank you!` |
| `/messages` | View recent user messages | `/messages` |

---

## ⚙️ Configuration

Edit `bot.py` to customize:

```python
entrance_fee: int = 305           # Payment amount
referral_target: int = 500        # Referrals needed for free VIP
default_vip_days: int = 30        # VIP duration in days
vip_channel_link: str = "..."    # Your VIP channel link
pay_link: str = "..."             # Payment link
```

---

## 🛡️ Security Features

✅ Environment variables for sensitive data  
✅ `.gitignore` protects secrets  
✅ PostgreSQL with connection pooling  
✅ Admin-only commands  
✅ Input validation  
✅ Error handling  

---

## 📊 Monitoring

### Railway Logs
```bash
# View live logs
railway logs

# View recent logs
railway logs --tail 100
```

### Health Checks
- Monitor active users: `/stats`
- Check database connection in logs
- Monitor Railway metrics dashboard

---

## 🆘 Troubleshooting

### Bot not starting
1. Check Railway logs for errors
2. Verify `DATABASE_URL` is set
3. Ensure `BOT_TOKEN` is correct
4. Check PostgreSQL is running

### Database connection failed
1. Verify PostgreSQL service is active
2. Check `DATABASE_URL` format
3. Ensure Railway PostgreSQL is in same project

### Referrals not working
1. Check database for foreign key constraints
2. Verify referral code generation
3. Test with `/status` command

---

## 🔄 Updates and Maintenance

### Update Bot Code
```bash
git pull origin main
# Railway auto-deploys on push
```

### Database Backup
Railway PostgreSQL includes automatic backups. Manual backup:
```bash
# Use Railway dashboard → Database → Backups
```

### Scale Bot
Railway auto-scales. For heavy load:
1. Increase PostgreSQL plan
2. Enable connection pooling (already implemented)
3. Monitor Railway metrics

---

## 📝 Changelog

### v2.0.0 (Current)
- ✅ Migrated to PostgreSQL
- ✅ Railway deployment ready
- ✅ Referral notifications
- ✅ Removed "Share to Friends" button
- ✅ Connection pooling
- ✅ Better error handling

### v1.0.0
- ✅ Basic bot functionality
- ✅ SQLite database
- ✅ Referral system

---

## 📄 License

This project is private. All rights reserved.

---

## 🤝 Support

For issues or questions:
- Contact: @PinayWalkerManilaBot
- GitHub Issues: [Create Issue](https://github.com/yourusername/vip-access-bot/issues)

---

## 🎉 Credits

Built with:
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [PostgreSQL](https://www.postgresql.org/)
- [Railway](https://railway.app)

---

**Made with ❤️ for VIP Access Management**
