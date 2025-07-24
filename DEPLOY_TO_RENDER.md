# 🚀 Easy Render.com Deployment Guide

## Quick Setup (5 minutes)

### 1. Prerequisites
- GitHub repository with this code
- Render.com account (free tier available)
- BingX API credentials

### 2. Deploy to Render

#### Option A: Using render-simple.yaml (Recommended)
1. **Fork/Push to GitHub**: Make sure your code is in a GitHub repository
2. **Connect to Render**: 
   - Go to [render.com](https://render.com)
   - Click "New +" → "Blueprint"
   - Connect your GitHub repository
   - Select `render-simple.yaml` as the blueprint file
3. **Set Environment Variables** (in Render dashboard):
   ```
   BINGX_API_KEY=your_bingx_api_key_here
   BINGX_SECRET_KEY=your_bingx_secret_key_here
   ```
4. **Deploy**: Click "Apply" and wait for deployment

#### Option B: Manual Web Service Setup
1. **Create Web Service**:
   - Go to Render dashboard
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   
2. **Configure Service**:
   - **Name**: `bingx-trading-bot`
   - **Runtime**: `Python 3`
   - **Build Command**: 
     ```bash
     pip install --upgrade pip && pip install -r requirements.txt && mkdir -p logs
     ```
   - **Start Command**: 
     ```bash
     python start_render.py
     ```

3. **Add PostgreSQL Database**:
   - In Render dashboard, create "PostgreSQL" service
   - Name it `bingx-db`
   - Connect it to your web service

### 3. Environment Variables
Set these in Render dashboard under "Environment":

#### Required
```bash
BINGX_API_KEY=your_api_key_here
BINGX_SECRET_KEY=your_secret_key_here
DATABASE_URL=postgresql://... (auto-set by Render)
```

#### Optional (with defaults)
```bash
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
MAX_CONCURRENT_TRADES=5
MIN_ORDER_SIZE_USDT=10.0
SCAN_INTERVAL_SECONDS=30
```

### 4. Access Your Bot
- **Web Dashboard**: `https://your-app-name.onrender.com`
- **API Docs**: `https://your-app-name.onrender.com/docs`
- **Health Check**: `https://your-app-name.onrender.com/health`

## 🎯 What Gets Deployed

✅ **Web Dashboard**: Complete PyScript frontend with 3 tabs
✅ **REST API**: All endpoints for bot control and data
✅ **WebSocket**: Real-time updates
✅ **Trading Bot**: Automated scanning and trading
✅ **Database**: PostgreSQL with all models
✅ **Static Files**: CSS, JS, and frontend assets

## 💰 Cost Estimate

**Free Tier** (suitable for testing):
- Web Service: Free (with limitations)
- PostgreSQL: Free (1GB limit)
- Total: **$0/month**

**Starter Plan** (recommended for production):
- Web Service: $7/month
- PostgreSQL: $7/month  
- Total: **$14/month**

## 🔧 Customization

### Trading Parameters
Edit environment variables in Render dashboard:
```bash
MAX_CONCURRENT_TRADES=3          # Reduce for safety
MIN_ORDER_SIZE_USDT=20.0         # Increase minimum order
INITIAL_STOP_LOSS_PERCENT=0.015  # Tighter stop loss
```

### Performance
For higher performance, upgrade to:
- **Standard Plan**: $25/month (better CPU/memory)
- **Pro Plan**: $85/month (dedicated resources)

## 🚨 Security Notes

1. **Never commit API keys** to GitHub
2. **Use environment variables** for all secrets
3. **Enable 2FA** on your Render account
4. **Monitor logs** for suspicious activity
5. **Start with testnet** (`BINGX_TESTNET=true`)

## 📊 Monitoring

**Built-in Monitoring**:
- Render provides logs, metrics, and uptime monitoring
- Access via Render dashboard → your service → "Logs" tab

**Custom Monitoring**:
- Health check endpoint: `/health`
- Bot status: `/api/bot/status`
- Dashboard summary: `/api/dashboard/summary`

## 🐛 Troubleshooting

### Common Issues

**Build Fails**:
```bash
# Check requirements.txt is valid
pip install -r requirements.txt
```

**Database Connection Error**:
- Verify PostgreSQL service is connected
- Check DATABASE_URL environment variable

**API Key Error**:
- Verify BingX API credentials in environment variables
- Test with BINGX_TESTNET=true first

**Memory Issues**:
- Upgrade to Starter plan ($7/month)
- Reduce MAX_CONCURRENT_TRADES

### Logs
View logs in Render dashboard:
```
Dashboard → Your Service → Logs
```

## 🎉 Success!

Once deployed, you should see:
1. ✅ Build completed successfully
2. ✅ Service is live and healthy
3. ✅ Database connected
4. ✅ Web dashboard accessible
5. ✅ Trading bot initializing

Visit your dashboard URL and start trading! 🚀

---

## Need Help?

- **Render Docs**: https://render.com/docs
- **BingX API Docs**: https://bingx-api.github.io/docs/
- **Issues**: Check the application logs in Render dashboard