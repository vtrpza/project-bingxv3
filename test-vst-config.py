#!/usr/bin/env python3
"""Test VST-only configuration"""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_vst_config():
    """Test that the bot is configured for VST-only trading"""
    print("🧪 Testing VST-only configuration...")
    
    # Test trading config
    from config.trading_config import TradingConfig
    
    print(f"✅ MAX_CONCURRENT_TRADES: {TradingConfig.MAX_CONCURRENT_TRADES}")
    print(f"✅ MAX_ASSETS_TO_SCAN: {TradingConfig.MAX_ASSETS_TO_SCAN}")
    print(f"✅ SCAN_INTERVAL_SECONDS: {TradingConfig.SCAN_INTERVAL_SECONDS}")
    print(f"✅ MAX_POSITION_SIZE_PERCENT: {TradingConfig.MAX_POSITION_SIZE_PERCENT}")
    
    # Test scanner VST filtering
    from scanner.initial_scanner import InitialScanner
    scanner = InitialScanner()
    
    # Test market filtering
    test_markets = [
        {'symbol': 'BTC/USDT', 'active': True},
        {'symbol': 'VST/USDT', 'active': True},  # This should be selected
        {'symbol': 'ETH/USDT', 'active': True},
    ]
    
    symbols = scanner._extract_usdt_symbols(test_markets)
    print(f"✅ Filtered symbols: {symbols}")
    
    if symbols == ['VST/USDT']:
        print("🎉 VST-only configuration is working correctly!")
        return True
    else:
        print(f"❌ Expected ['VST/USDT'], got {symbols}")
        return False

def test_database_config():
    """Test database configuration"""
    print("\n🧪 Testing database configuration...")
    
    # Test environment without DATABASE_URL (should use SQLite)
    import os
    old_db_url = os.environ.get('DATABASE_URL')
    if 'DATABASE_URL' in os.environ:
        del os.environ['DATABASE_URL']
    
    from database.connection import DatabaseManager
    db = DatabaseManager()
    
    try:
        if db.initialize():
            print("✅ Database initialization successful")
            if hasattr(db, 'is_sqlite') and db.is_sqlite:
                print("✅ Using SQLite for local development")
            else:
                print("✅ Using PostgreSQL")
            return True
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    finally:
        # Restore environment
        if old_db_url:
            os.environ['DATABASE_URL'] = old_db_url

def main():
    print("🤖 VST Trading Bot - Configuration Test")
    print("=" * 50)
    
    success = True
    
    if not test_vst_config():
        success = False
    
    if not test_database_config():
        success = False
    
    if success:
        print("\n🎉 All tests passed! VST-only configuration is ready!")
    else:
        print("\n❌ Some tests failed. Check configuration.")
        sys.exit(1)

if __name__ == "__main__":
    main()