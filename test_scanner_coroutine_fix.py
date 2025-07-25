#!/usr/bin/env python3
"""Test script to verify the coroutine fix in scanner worker."""

import asyncio
import sys
import os
from datetime import datetime

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from scanner.worker import ScannerWorker
from database.connection import init_database
from api.client import initialize_client
from utils.logger import get_logger

logger = get_logger(__name__)


async def test_scanner_fix():
    """Test the scanner worker to ensure coroutine issues are fixed."""
    try:
        logger.info("=== Testing Scanner Worker Coroutine Fix ===")
        
        # Initialize database
        if not init_database():
            logger.error("Failed to initialize database")
            return False
        
        # Initialize API client
        if not await initialize_client():
            logger.error("Failed to initialize API client")
            return False
        
        # Create scanner worker
        worker = ScannerWorker()
        
        logger.info("Running a single scan cycle to test for coroutine errors...")
        
        # Run one scan cycle
        await worker.scan_cycle()
        
        logger.info("✅ Scan cycle completed without coroutine errors!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    success = await test_scanner_fix()
    
    if success:
        logger.info("✅ All tests passed! The coroutine issue has been fixed.")
        sys.exit(0)
    else:
        logger.error("❌ Tests failed. Please check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())