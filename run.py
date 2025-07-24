#!/usr/bin/env python3
# run.py
"""Simple script to run the BingX Trading Bot"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    # Import and run main
    from main import main
    import asyncio
    
    print("🤖 Starting BingX Trading Bot...")
    print("📝 Make sure you have configured your .env file with API keys!")
    print("📋 Press Ctrl+C to stop the bot")
    print("-" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)