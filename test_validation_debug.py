#!/usr/bin/env python3
"""
Debug validation logic to find why all assets are being marked as INVALID
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scanner.validator import AssetValidator, ValidationCriteria
from api.market_data import MarketDataAPI

async def test_validation():
    """Test the validation logic directly"""
    print("🔍 Testing Asset Validation Logic")
    
    # Initialize components
    validator = AssetValidator()
    
    # Test popular symbols
    test_symbols = ["BTC/USDT", "ETH/USDT", "$1/USDT", "AAVE/USDT"]
    
    for symbol in test_symbols:
        print(f"\n📊 Testing {symbol}:")
        try:
            result = await validator.validate_asset(symbol)
            print(f"   is_valid: {result['is_valid']}")
            print(f"   reason: {result.get('reason', 'No reason')}")
            print(f"   validation_data keys: {list(result.get('validation_data', {}).keys())}")
            
            # Check validation checks specifically
            validation_data = result.get('validation_data', {})
            validation_checks = validation_data.get('validation_checks', {})
            print(f"   validation_checks: {validation_checks}")
            
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_validation())