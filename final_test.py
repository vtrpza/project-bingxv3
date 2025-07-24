#!/usr/bin/env python3
# final_test.py
"""Final system validation before deployment."""

import asyncio
import os
import sys
import yaml
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.connection import init_database, create_tables, get_session
from api.client import BingXClient
from scanner.initial_scanner import InitialScanner
from utils.converters import convert_decimals
from utils.maintenance_worker import MaintenanceWorker
from decimal import Decimal


async def test_full_system():
    """Comprehensive system test."""
    print("🚀 BingX Trading Bot - Final System Test")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 6
    
    # Test 1: Database
    print("\n1. 🗄️ Testing database connection...")
    try:
        if not init_database():
            raise RuntimeError("Database initialization failed")
        if not create_tables():
            raise RuntimeError("Table creation failed")
        
        with get_session() as session:
            from sqlalchemy import text
            result = session.execute(text("SELECT COUNT(*) FROM assets")).scalar()
            print(f"   ✅ Database OK - {result} assets in database")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Database test failed: {e}")
    
    # Test 2: API Connection
    print("\n2. 🌐 Testing BingX API...")
    try:
        client = BingXClient()
        success = await client.initialize()
        if success:
            balance = await client.fetch_balance()
            print(f"   ✅ API OK - Connection established")
            tests_passed += 1
        else:
            print(f"   ❌ API connection failed")
    except Exception as e:
        print(f"   ❌ API test failed: {e}")
    
    # Test 3: Decimal Converters
    print("\n3. 🔧 Testing utility functions...")
    try:
        test_data = {
            'price': Decimal('100.50'),
            'nested': {'amount': Decimal('25.75')}
        }
        converted = convert_decimals(test_data)
        assert isinstance(converted['price'], float)
        assert isinstance(converted['nested']['amount'], float)
        print("   ✅ Converters OK - Decimal serialization working")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Converters test failed: {e}")
    
    # Test 4: Scanner Basic
    print("\n4. 🔍 Testing scanner functionality...")
    try:
        scanner = InitialScanner()
        # Test symbol extraction
        test_markets = [
            {'symbol': 'BTC/USDT', 'active': True, 'quote': 'USDT'},
            {'symbol': 'ETH/USDT', 'active': True, 'quote': 'USDT'},
        ]
        symbols = scanner._extract_usdt_symbols(test_markets)
        if len(symbols) >= 2:
            print(f"   ✅ Scanner OK - Extracted {len(symbols)} symbols")
            tests_passed += 1
        else:
            print("   ❌ Scanner failed - No symbols extracted")
    except Exception as e:
        print(f"   ❌ Scanner test failed: {e}")
    
    # Test 5: Render Configuration  
    print("\n5. 📋 Testing render.yaml...")
    try:
        with open('render.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate structure
        assert 'services' in config
        assert 'databases' in config
        
        services = config['services']
        service_types = [s.get('type') for s in services]
        
        # Check for required service types
        required_types = ['web', 'worker', 'redis']
        for req_type in required_types:
            if req_type not in service_types:
                raise ValueError(f"Missing service type: {req_type}")
        
        print(f"   ✅ Render config OK - {len(services)} services configured")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Render config test failed: {e}")
    
    # Test 6: Maintenance Worker
    print("\n6. 🛠️ Testing maintenance worker...")
    try:
        worker = MaintenanceWorker()
        status = await worker.get_status()
        
        assert 'schedule' in status
        assert 'next_tasks' in status
        
        print("   ✅ Maintenance worker OK - Schedule configured")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Maintenance worker test failed: {e}")
    
    # Summary
    print(f"\n{'=' * 60}")
    print(f"🏁 FINAL TEST RESULTS")
    print(f"{'=' * 60}")
    
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("🎉 ALL TESTS PASSED! System is ready for deployment.")
        print("\n📋 Deployment checklist:")
        print("   ✅ Database initialization fixed")
        print("   ✅ JSON serialization errors resolved")
        print("   ✅ Symbol filtering implemented")
        print("   ✅ Render.yaml configuration corrected")
        print("   ✅ Maintenance workers created")
        print("   ✅ API connection working")
        
        print("\n🚀 Next steps:")
        print("   1. Set environment variables in Render dashboard")
        print("   2. Deploy using render.yaml")
        print("   3. Monitor logs for successful startup")
        print("   4. Verify trading signals generation")
        
        return True
    else:
        failed = total_tests - tests_passed
        print(f"⚠️ {failed} test(s) failed. Please fix issues before deployment.")
        return False


def show_system_info():
    """Show system information."""
    print("\n📊 System Information:")
    print(f"   - Python version: {sys.version.split()[0]}")
    print(f"   - Project root: {Path.cwd()}")
    print(f"   - Environment: {'Production' if os.getenv('RENDER') else 'Development'}")
    
    # Check required files
    required_files = [
        'main.py', 'requirements.txt', 'render.yaml',
        'database/models.py', 'api/client.py', 'scanner/initial_scanner.py'
    ]
    
    print("\n📁 Required files:")
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} (missing)")


if __name__ == "__main__":
    try:
        # Show system info
        show_system_info()
        
        # Set minimal env vars for testing
        os.environ.setdefault('DB_HOST', 'localhost')
        os.environ.setdefault('DB_PORT', '5432')
        os.environ.setdefault('DB_NAME', 'bingx_trading')
        os.environ.setdefault('DB_USER', 'trading_bot')
        
        # Run comprehensive test
        success = asyncio.run(test_full_system())
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test runner error: {e}")
        sys.exit(1)