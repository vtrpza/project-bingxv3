# 🚀 BingX Trading Bot - Quick Start Guide

Get your BingX Trading Bot up and running locally in minutes!

## 🎯 Quick Commands (TL;DR)

```bash
# 1. Clone and setup
git clone <your-repo>
cd project-bingxv3

# 2. Quick start (web interface only)
./start.sh

# 3. Or start everything
./start.sh full

# 4. Access dashboard
open http://localhost:8000
```

## 📋 Prerequisites

- **Python 3.11+** ([Download](https://python.org))
- **PostgreSQL 16+** ([Download](https://postgresql.org)) OR **Docker** ([Download](https://docker.com))
- **BingX Account** with API keys ([Get them here](https://bingx.com/en-us/account/api))

## 🏃‍♂️ Quick Start Options

### Option 1: Super Quick (Web Only) - 2 minutes ⚡

```bash
# 1. Download the project
git clone <your-repo-url>
cd project-bingxv3

# 2. Start web interface only
./start.sh

# 3. Open browser
open http://localhost:8000
```

**What you get:**
- ✅ Web dashboard
- ✅ API documentation
- ✅ Basic monitoring
- ❌ No live trading data (needs API keys)

### Option 2: Full Experience - 5 minutes 🔥

```bash
# 1. Setup environment
./start.sh --setup

# 2. Edit API credentials
nano .env  # Add your BingX API keys

# 3. Start all components
./start.sh full

# 4. Open dashboard
open http://localhost:8000
```

**What you get:**
- ✅ Complete trading bot
- ✅ Live market data
- ✅ Real-time analysis
- ✅ Trading signals
- ✅ Portfolio tracking

### Option 3: Docker Everything - 3 minutes 🐳

```bash
# 1. Start with Docker
./start.sh docker

# 2. Edit API credentials (in another terminal)
nano .env

# 3. Restart to apply changes
./start.sh docker
```

**What you get:**
- ✅ Isolated environment
- ✅ PostgreSQL + Redis included
- ✅ Production-like setup
- ✅ Easy cleanup

## 🔧 Detailed Setup

### Step 1: Environment Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd project-bingxv3

# Make scripts executable (if needed)
chmod +x start.sh test.sh
```

### Step 2: Get BingX API Keys

1. Go to [BingX API Management](https://bingx.com/en-us/account/api)
2. Create new API key
3. **Important:** Use **TESTNET** credentials for development!
4. Copy API Key and Secret Key

### Step 3: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required settings:**
```bash
# Your BingX API credentials
BINGX_API_KEY=your_testnet_api_key_here
BINGX_SECRET_KEY=your_testnet_secret_key_here

# Use testnet for safety
BINGX_TESTNET=True
PAPER_TRADING=True
TRADING_ENABLED=False  # Start with trading disabled
```

### Step 4: Choose Your Running Method

#### A) Simple Python (Recommended for Development)

```bash
# Install dependencies and start
./start.sh --setup
./start.sh full
```

#### B) Docker Compose (Recommended for Production-like Testing)

```bash
# Start with Docker
./start.sh docker
```

#### C) Manual Step-by-Step

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Start PostgreSQL (with Docker)
docker run -d --name bingx_postgres \
  -e POSTGRES_DB=bingx_trading \
  -e POSTGRES_USER=trading_user \
  -e POSTGRES_PASSWORD=trading_password \
  -p 5432:5432 postgres:16-alpine

# 3. Run database migrations
python -m alembic upgrade head

# 4. Start components manually
python -m uvicorn api.web_api:app --reload &
python -m scanner.initial_scanner &
python -m analysis.worker &
python -m trading.worker &
```

## 🎮 Using the Dashboard

Once started, open your browser to **http://localhost:8000**

### 📊 Scanner Tab
- View validated assets
- Monitor real-time indicators (MM1, Center, RSI)
- See trading signals as they're generated
- Track volume analysis

### 💰 Trading Tab  
- Monitor active positions
- View P&L in real-time
- Check trade history
- Manage risk settings

### 📈 Analytics Tab
- Performance metrics
- Success rates
- Portfolio analytics
- Historical data

## 🧪 Testing Your Setup

```bash
# Run all tests
./test.sh

# Test specific components
./test.sh db        # Database connection
./test.sh api       # API configuration  
./test.sh ccxt      # BingX connection
./test.sh unit      # Unit tests only
```

## 🔧 Configuration Options

### Trading Safety Settings (Recommended for Development)

```bash
# In your .env file:
PAPER_TRADING=True           # Simulate trades only
TRADING_ENABLED=False        # Disable actual trading
BINGX_TESTNET=True          # Use testnet environment
MAX_CONCURRENT_TRADES=3      # Limit simultaneous trades
MAX_DAILY_LOSS_PERCENT=2.0   # Maximum daily loss
```

### Performance Settings

```bash
# For faster development
SCAN_INTERVAL_SECONDS=60     # How often to scan markets
MAX_ASSETS_TO_SCAN=50        # Limit number of assets
DEBUG=True                   # Enable debug logging
```

## 📊 Monitoring & Logs

### View Logs
```bash
# Real-time logs
tail -f logs/trading_bot.log

# Error logs only
grep ERROR logs/trading_bot.log

# Trading activity
grep "TRADE" logs/trading_bot.log
```

### Health Checks
```bash
# API health
curl http://localhost:8000/health

# Database status
./test.sh db

# All components
./test.sh
```

## 🛑 Stopping the Bot

```bash
# Stop all components
Ctrl+C  # In the terminal where you started

# Or if running in background
pkill -f "python -m"

# Stop Docker containers
docker-compose down
```

## 🐛 Troubleshooting

### Common Issues

#### "Database connection failed"
```bash
# Check if PostgreSQL is running
./test.sh db

# Restart PostgreSQL with Docker
docker restart bingx_postgres_dev
```

#### "API connection failed"
```bash
# Test your API credentials
./test.sh ccxt

# Check if API keys are set in .env
grep BINGX_API_KEY .env
```

#### "Permission denied: ./start.sh"
```bash
# Make script executable
chmod +x start.sh test.sh
```

#### "Module not found"
```bash
# Install missing dependencies
pip install -r requirements.txt

# Check Python path
export PYTHONPATH=$(pwd)
```

### Getting Help

1. **Check logs:** `tail -f logs/trading_bot.log`
2. **Run tests:** `./test.sh all`
3. **Validate config:** `./test.sh api`
4. **Test database:** `./test.sh db`

## 🎯 Next Steps

### For Development
1. **Enable safe trading:** Set `TRADING_ENABLED=True` with `PAPER_TRADING=True`
2. **Add your strategies:** Modify files in `analysis/signals.py`
3. **Customize UI:** Edit files in `frontend/`
4. **Add new indicators:** Extend `analysis/indicators.py`

### For Production
1. **Use real API keys:** Switch from testnet to production
2. **Enable trading:** Set `PAPER_TRADING=False`
3. **Configure alerts:** Set up Telegram notifications
4. **Deploy:** Use the included `render.yaml` for Render.com

## 📚 Additional Resources

### Project Structure
```
project-bingxv3/
├── api/              # Web API and WebSocket
├── scanner/          # Asset scanning and validation
├── analysis/         # Technical analysis and signals
├── trading/          # Order execution and risk management
├── database/         # Database models and migrations
├── frontend/         # PyScript web interface
├── config/           # Configuration management
├── utils/            # Shared utilities
├── tests/            # Test suites
├── start.sh          # Quick start script
├── test.sh           # Testing script
└── docker-compose.yml # Docker setup
```

### Key URLs (when running)
- **Dashboard:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health
- **pgAdmin:** http://localhost:5050 (if using Docker dev setup)

### Configuration Files
- `.env` - Main configuration
- `.env.dev` - Development defaults
- `docker-compose.dev.yml` - Development Docker setup
- `requirements.txt` - Python dependencies

## 🚨 Safety Reminders

- ⚠️ **Always use TESTNET for development**
- ⚠️ **Start with PAPER_TRADING=True**
- ⚠️ **Never commit API keys to git**
- ⚠️ **Set conservative risk limits**
- ⚠️ **Monitor your first trades closely**

---

## 🎉 You're Ready!

Your BingX Trading Bot is now running! Start with the web interface, configure your API keys safely, and begin exploring the powerful features of your automated trading system.

**Happy Trading! 🚀**