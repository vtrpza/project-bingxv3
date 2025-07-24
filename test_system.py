#!/usr/bin/env python3
# test_system.py
"""Quick system validation test."""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.connection import init_database, create_tables, get_session
from api.client import BingXClient
from api.market_data import get_market_data_api
from scanner.initial_scanner import InitialScanner
from utils.converters import convert_decimals
from decimal import Decimal


async def test_database():
    """Test database initialization and basic operations."""
    print("🔄 Testing database...")
    
    try:
        # Initialize database
        if not init_database():
            raise RuntimeError("Failed to initialize database")
        
        # Create tables
        if not create_tables():
            raise RuntimeError("Failed to create tables")
        
        # Test session
        with get_session() as session:
            from sqlalchemy import text
            result = session.execute(text("SELECT 1")).scalar()
            if result != 1:
                raise RuntimeError("Database query failed")
        
        print("✅ Database test passed")
        return True
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


async def test_api_connection():
    """Test BingX API connection."""
    print("🔄 Testing API connection...")
    
    try:
        client = BingXClient()
        success = await client.initialize()
        
        if not success:
            raise RuntimeError("Client initialization failed")
        
        # Test a simple API call
        balance = await client.fetch_balance()
        
        print("✅ API connection test passed")
        return True
        
    except Exception as e:
        print(f"❌ API connection test failed: {e}")
        return False


def test_converters():
    """Test decimal conversion utilities."""
    print("🔄 Testing decimal converters...")
    
    try:
        # Test data with Decimals
        test_data = {
            'price': Decimal('42000.50'),
            'volume': Decimal('1234567.89'),
            'nested': {
                'value': Decimal('123.45'),
                'list': [Decimal('1.0'), Decimal('2.0')]
            }
        }
        
        # Convert decimals
        converted = convert_decimals(test_data)
        
        # Verify conversion
        assert isinstance(converted['price'], float)
        assert isinstance(converted['volume'], float)
        assert isinstance(converted['nested']['value'], float)
        assert isinstance(converted['nested']['list'][0], float)
        
        print("✅ Decimal converters test passed")
        return True
        
    except Exception as e:
        print(f"❌ Decimal converters test failed: {e}")
        return False


async def test_scanner_basic():
    """Test basic scanner functionality without full scan."""
    print("🔄 Testing scanner...")
    
    try:
        # Test market data API
        market_api = get_market_data_api()
        
        # Test getting valid symbols (with fallback)
        valid_symbols = await market_api.get_valid_symbols()
        
        if not valid_symbols:
            raise RuntimeError("No valid symbols returned")
        
        print(f"✅ Scanner test passed - Found {len(valid_symbols)} valid symbols")
        return True
        
    except Exception as e:
        print(f"❌ Scanner test failed: {e}")
        return False


async def run_system_tests():
    """Run all system validation tests."""
    print("🚀 Starting BingX Trading Bot System Tests\n")
    
    tests = [
        ("Database", test_database),
        ("API Connection", test_api_connection), 
        ("Decimal Converters", lambda: test_converters()),
        ("Scanner Basic", test_scanner_basic),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} Test ---")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} test error: {e}")
            results[test_name] = False
    
    # Summary
    print(f"\n{'='*50}")
    print("🏁 TEST SUMMARY")
    print(f"{'='*50}")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
    
    print(f"\nResult: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! System is ready.")
        return True
    else:
        print("⚠️ Some tests failed. Check errors above.")
        return False


if __name__ == "__main__":
    try:
        # Set basic env vars if not set (for testing)
        os.environ.setdefault('DB_HOST', 'localhost')
        os.environ.setdefault('DB_PORT', '5432')
        os.environ.setdefault('DB_NAME', 'bingx_trading')
        os.environ.setdefault('DB_USER', 'trading_bot')
        
        success = asyncio.run(run_system_tests())
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test runner error: {e}")
        sys.exit(1)