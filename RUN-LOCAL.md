# 🚀 Run VST Bot Locally - Super Easy

## 1-Step Setup

Just run this script:
```bash
python run-local.py
```

**That's it!** The script automatically:
- Sets development environment
- Uses SQLite database (no setup needed)
- Loads your API keys from `.env` file
- Runs the VST-only bot

## First Time Setup

If you don't have `.env` file yet:
```bash
python easy-deploy.py  # Creates .env file
# Edit .env with your BingX API keys
python run-local.py    # Run the bot
```

## What You'll See

```
🤖 VST Trading Bot - Local Runner
========================================
✅ Environment file loaded
✅ Development environment configured
✅ API keys found
✅ Database: SQLite (vst_trading.db)
✅ Environment: Development
✅ VST-only mode: Active

🚀 Starting VST Trading Bot...
Press Ctrl+C to stop
----------------------------------------
```

Then the bot will start monitoring VST/USDT!

## Stop the Bot

Press `Ctrl+C` to stop safely.

---

**No more environment errors!** The script handles everything automatically. 🎉