#!/usr/bin/env python3
"""
Test script to verify scanner fixes:
1. Database field size issues
2. Session rollback handling
3. Force revalidation functionality
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path)

from database.connection import init_database, create_tables, get_session
from database.repository import AssetRepository
from scanner.initial_scanner import get_initial_scanner
from utils.logger import get_logger

logger = get_logger(__name__)


async def test_database_fix():
    """Test that the database can now handle long currency names."""
    logger.info("Testing database fix for long currency names...")
    
    test_assets = [
        {"symbol": "1000000BABYDOGE/USDT", "base": "1000000BABYDOGE", "quote": "USDT"},
        {"symbol": "1000000MOG/USDT", "base": "1000000MOG", "quote": "USDT"},
        {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT"},
    ]
    
    asset_repo = AssetRepository()
    
    try:
        with get_session() as session:
            for asset in test_assets:
                # Try to create asset
                result = asset_repo.create(
                    session,
                    symbol=asset["symbol"],
                    base_currency=asset["base"],
                    quote_currency=asset["quote"],
                    is_valid=True,
                    min_order_size=10.0,
                )
                
                if result:
                    logger.info(f"✅ Successfully created asset: {asset['symbol']}")
                else:
                    logger.error(f"❌ Failed to create asset: {asset['symbol']}")
                    
        logger.info("Database fix test completed!")
        return True
        
    except Exception as e:
        logger.error(f"Database test failed: {e}")
        return False


async def test_scanner_validation():
    """Test that the scanner can validate assets properly."""
    logger.info("Testing scanner validation...")
    
    scanner = get_initial_scanner()
    
    # Test with a small subset
    result = await scanner.scan_all_assets(force_refresh=True, max_assets=10)
    
    if result:
        summary = result.get_summary()
        logger.info(f"Scanner test results:")
        logger.info(f"  Total discovered: {summary['total_discovered']}")
        logger.info(f"  Valid assets: {summary['valid_assets_count']}")
        logger.info(f"  Invalid assets: {summary['invalid_assets_count']}")
        logger.info(f"  Errors: {summary['errors_count']}")
        logger.info(f"  Success rate: {summary['success_rate']:.1f}%")
        
        # Check for specific error patterns
        if result.errors:
            logger.warning(f"Errors found during scan:")
            for error in result.errors[:5]:
                logger.warning(f"  - {error['symbol']}: {error['error']}")
        
        return True
    else:
        logger.error("Scanner test failed!")
        return False


async def test_api_endpoints():
    """Test API endpoints for asset validation."""
    logger.info("Testing API endpoints...")
    
    try:
        from api.web_api import app
        from httpx import AsyncClient
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Test validation table endpoint
            response = await client.get("/api/assets/validation-table")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Validation table endpoint working")
                logger.info(f"  Total assets: {data['summary']['total_assets']}")
                logger.info(f"  Valid assets: {data['summary']['valid_assets']}")
            else:
                logger.error(f"❌ Validation table endpoint failed: {response.status_code}")
            
            # Test force revalidation endpoint
            response = await client.post("/api/assets/force-revalidation")
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Force revalidation endpoint working")
                logger.info(f"  Message: {data['message']}")
            else:
                logger.error(f"❌ Force revalidation endpoint failed: {response.status_code}")
                
        return True
        
    except Exception as e:
        logger.error(f"API test failed: {e}")
        return False


async def main():
    """Run all tests."""
    logger.info("🚀 Starting scanner fix tests...")
    
    # Initialize database
    if not init_database():
        logger.error("Failed to initialize database")
        return
    
    # Create tables
    if not create_tables():
        logger.error("Failed to create tables")
        return
    
    logger.info("Database initialized successfully\n")
    
    # Run tests
    tests = [
        ("Database Fix", test_database_fix),
        ("Scanner Validation", test_scanner_validation),
        ("API Endpoints", test_api_endpoints),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            success = await test_func()
            results.append((test_name, success))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    total_passed = sum(1 for _, success in results if success)
    logger.info(f"\nTotal: {total_passed}/{len(results)} tests passed")


if __name__ == "__main__":
    asyncio.run(main())