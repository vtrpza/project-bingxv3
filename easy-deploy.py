#!/usr/bin/env python3
"""
VST Trading Bot - Easy Deployment Setup
No database passwords needed! 
"""

import os
import sys
from pathlib import Path

def create_simple_env():
    """Create a simple .env file for local testing"""
    env_content = """# VST Trading Bot - Simple Configuration
# Only set BINGX_API_KEY and BINGX_SECRET_KEY - everything else is auto-configured

# ==========================================
# REQUIRED: SET YOUR BINGX API CREDENTIALS
# ==========================================
BINGX_API_KEY=your_api_key_here
BINGX_SECRET_KEY=your_secret_key_here

# ==========================================
# VST-ONLY CONFIGURATION (Already optimized)
# ==========================================
MAX_CONCURRENT_TRADES=1
MAX_ASSETS_TO_SCAN=1
SCAN_INTERVAL_SECONDS=15
TRADING_ENABLED=true
PAPER_TRADING=false

# ==========================================
# DATABASE (Auto-configured for Render)
# ==========================================
# For local testing (optional):
# DATABASE_URL=sqlite:///vst_trading.db

# ==========================================
# LOGGING
# ==========================================
LOG_LEVEL=INFO
DEBUG=false

# ==========================================
# RISK MANAGEMENT (Conservative defaults)
# ==========================================
INITIAL_STOP_LOSS_PERCENT=0.02
MAX_POSITION_SIZE_PERCENT=10.0
"""
    
    env_file = Path('.env')
    if env_file.exists():
        print("⚠️  .env file already exists")
        try:
            choice = input("Overwrite? (y/n): ").lower().strip()
            if choice != 'y':
                print("❌ Aborted")
                return False
        except EOFError:
            print("⚠️  Non-interactive environment detected, backing up existing .env")
            import shutil
            shutil.copy('.env', '.env.backup')
            print("✅ Backed up existing .env to .env.backup")
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("✅ Created .env file")
    return True

def show_deployment_instructions():
    """Show simple deployment instructions"""
    print(f"""
🚀 VST Trading Bot - Easy Deployment Instructions

📋 STEP 1: Set up your BingX API Keys
   1. Go to https://bingx.com/en-us/account/api-management
   2. Create API key with trading permissions
   3. Edit .env file and set:
      BINGX_API_KEY=your_actual_key
      BINGX_SECRET_KEY=your_actual_secret

📋 STEP 2: Deploy to Render (No database password needed!)
   1. Create Render account: https://render.com
   2. Connect your GitHub repository  
   3. Create new "Web Service"
   4. Use file: render-easy.yaml
   5. Set environment variables in Render dashboard:
      - BINGX_API_KEY: your_api_key
      - BINGX_SECRET_KEY: your_secret_key
   6. Deploy! 🎉

📋 STEP 3: Test Locally (Optional)
   pip install -r requirements.txt
   python main.py

✨ Features:
   • VST-only trading (no other coins)
   • Auto database setup (no passwords!)
   • Conservative risk management
   • 15-second scanning interval
   • 10% max position size

🔧 Configuration files created:
   • .env (local configuration)
   • render-easy.yaml (deployment configuration)

⚠️  Remember to set your actual BingX API keys before deploying!
""")

def main():
    print("🤖 VST Trading Bot - Easy Setup")
    print("=" * 50)
    
    # Create simple environment file
    if create_simple_env():
        show_deployment_instructions()
    else:
        print("❌ Setup failed")
        sys.exit(1)

if __name__ == "__main__":
    main()