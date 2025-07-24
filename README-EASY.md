# 🤖 VST Trading Bot - Easy Deployment

**Simplified VST-only trading bot with automatic database setup!**

## 🚀 Quick Start (5 minutes)

### Step 1: Get Your BingX API Keys
1. Go to [BingX API Management](https://bingx.com/en-us/account/api-management)
2. Create new API key with **trading permissions**
3. Save your `API Key` and `Secret Key`

### Step 2: Easy Setup
```bash
python easy-deploy.py
```
This creates:
- `.env` file for local testing
- `render-easy.yaml` for deployment

### Step 3: Deploy to Render
1. Create account at [Render.com](https://render.com)
2. Connect your GitHub repository
3. Create "Web Service" 
4. Use `render-easy.yaml` as blueprint
5. Set environment variables:
   - `BINGX_API_KEY`: your_api_key_here
   - `BINGX_SECRET_KEY`: your_secret_key_here
6. Deploy! 🎉

**No database passwords needed!** Render handles everything automatically.

## ✨ Features

- **VST-only trading** (no other coins)
- **Automatic database setup** (no passwords!)
- **Fast 15-second scanning** 
- **Conservative risk management** (2% stop loss)
- **10% max position size** per trade
- **Only 1 concurrent trade** (focused)

## 🧪 Test Locally (Optional)

```bash
# Edit .env file with your API keys first
pip install -r requirements.txt
python main.py
```

Uses SQLite locally, PostgreSQL on Render automatically.

## ⚙️ Configuration

All optimized for VST trading:
- `MAX_CONCURRENT_TRADES=1` (VST only)
- `SCAN_INTERVAL_SECONDS=15` (fast)
- `MAX_POSITION_SIZE_PERCENT=10.0` (conservative)
- `INITIAL_STOP_LOSS_PERCENT=0.02` (2% stop loss)

## 📊 Trading Strategy

**3 Signal Rules:**
1. **MA Crossover**: MM1 crosses Center line (2h/4h) + RSI 35-73
2. **MA Distance**: MM1 ≥2% from Center (2h) or ≥3% (4h) 
3. **Volume Spike**: 2x average volume + direction from MAs

**Risk Management:**
- 2% initial stop loss
- Trailing stop at breakeven after 1.5% profit
- Progressive take profits at 3%, 5%, 8%, 12%

## 🔧 Files Created

- `render-easy.yaml` - Deployment configuration
- `.env` - Local environment variables
- `easy-deploy.py` - Setup script

## ❓ Need Help?

1. **Check logs** in Render dashboard
2. **Verify API keys** have trading permissions
3. **Check BingX API limits** (not exceeded)
4. **Ensure VST/USDT** is available on BingX

---

**Ready to trade VST? Just set your API keys and deploy!** 🚀