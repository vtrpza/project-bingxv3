# 🤖 BingX Trading Bot - Quick Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/YOUR_USERNAME/YOUR_REPO_NAME)

## ⚡ One-Click Deployment

1. **Click the "Deploy to Render" button above**
2. **Connect your GitHub account** (if not already connected)
3. **Set your API credentials**:
   - `BINGX_API_KEY`: Your BingX API key
   - `BINGX_SECRET_KEY`: Your BingX secret key
4. **Click "Apply"** and wait for deployment (3-5 minutes)
5. **Access your dashboard** at the provided URL

## 🎯 What You Get

- ✅ **Complete Trading Bot** with automated scanning and trading
- ✅ **Web Dashboard** with real-time data and controls  
- ✅ **PostgreSQL Database** for data persistence
- ✅ **Free Tier Available** - $0/month to start
- ✅ **Auto SSL Certificate** - Secure HTTPS access
- ✅ **Automatic Deployments** - Updates when you push to GitHub

## 📊 Live Demo

After deployment, your bot will be available at:
- **Dashboard**: `https://your-app-name.onrender.com`
- **API Docs**: `https://your-app-name.onrender.com/docs`
- **Health Check**: `https://your-app-name.onrender.com/health`

## 🔧 Configuration

All configuration is done through environment variables in the Render dashboard:

### Required
```
BINGX_API_KEY=your_api_key
BINGX_SECRET_KEY=your_secret_key
```

### Optional
```
MAX_CONCURRENT_TRADES=5
MIN_ORDER_SIZE_USDT=10.0
INITIAL_STOP_LOSS_PERCENT=0.02
SCAN_INTERVAL_SECONDS=30
LOG_LEVEL=INFO
```

## 💰 Pricing

- **Free Tier**: Perfect for testing ($0/month)
- **Starter Plan**: Recommended for live trading ($14/month)
- **Automatic scaling** based on usage

## 🛡️ Security

- ✅ **Environment Variables** - API keys never in code
- ✅ **HTTPS Only** - All traffic encrypted
- ✅ **Database Isolation** - Private PostgreSQL instance
- ✅ **Access Logs** - Monitor all activity

## 📞 Support

- **Documentation**: See `DEPLOY_TO_RENDER.md` for detailed setup
- **Issues**: Check application logs in Render dashboard
- **Updates**: Auto-deploy when you push to GitHub

---

**Ready to start trading?** Click the deploy button above! 🚀