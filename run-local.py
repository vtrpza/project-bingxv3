#!/usr/bin/env python3
"""
VST Trading Bot - Easy Local Runner
Automatically sets up environment and runs the bot locally
"""

import os
import sys
import subprocess
from pathlib import Path

def setup_environment():
    """Set up environment variables for local development"""
    os.environ['ENVIRONMENT'] = 'development'
    os.environ['DATABASE_URL'] = 'sqlite:///vst_trading.db'
    os.environ['DEBUG'] = 'true'
    os.environ['LOG_LEVEL'] = 'INFO'
    
    # Check if API keys are set
    if not os.environ.get('BINGX_API_KEY'):
        print("⚠️  BINGX_API_KEY not found in environment")
        print("Please set your API keys:")
        print("export BINGX_API_KEY=your_api_key")
        print("export BINGX_SECRET_KEY=your_secret_key")
        print("\nOr edit the .env file if it exists")
        return False
    
    if not os.environ.get('BINGX_SECRET_KEY'):
        print("⚠️  BINGX_SECRET_KEY not found in environment")
        print("Please set your API keys:")
        print("export BINGX_API_KEY=your_api_key")
        print("export BINGX_SECRET_KEY=your_secret_key")
        print("\nOr edit the .env file if it exists")
        return False
    
    return True

def load_env_file():
    """Load .env file if it exists"""
    env_file = Path('.env')
    if env_file.exists():
        print("📋 Loading .env file...")
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        return True
    return False

def main():
    print("🤖 VST Trading Bot - Local Runner")
    print("=" * 40)
    
    # Load .env file first
    env_loaded = load_env_file()
    if env_loaded:
        print("✅ Environment file loaded")
    
    # Set up development environment
    setup_environment()
    print("✅ Development environment configured")
    
    # Check API keys
    if not setup_environment():
        print("❌ Setup failed - missing API keys")
        sys.exit(1)
    
    print("✅ API keys found")
    print(f"✅ Database: SQLite (vst_trading.db)")
    print(f"✅ Environment: Development")
    print(f"✅ VST-only mode: Active")
    print()
    
    # Run the bot
    print("🚀 Starting VST Trading Bot...")
    print("Press Ctrl+C to stop")
    print("-" * 40)
    
    try:
        # Run main.py with the configured environment
        subprocess.run([sys.executable, 'main.py'], check=True)
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Bot failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()