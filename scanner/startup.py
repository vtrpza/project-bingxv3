#!/usr/bin/env python3
# scanner/startup.py
"""Startup script for scanner with automatic initialization and health checks."""

import asyncio
import sys
import os
import logging
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from database.connection import init_database, create_tables
from scanner.initial_scanner import get_initial_scanner
from scanner.enhanced_worker import EnhancedScannerWorker
from utils.logger import get_logger

logger = get_logger(__name__)


async def initialize_system():
    """Initialize database and perform initial asset scan if needed."""
    try:
        logger.info("🚀 Starting BingX Scanner System...")
        
        # Initialize database
        logger.info("📋 Initializing database...")
        if not init_database():
            logger.error("❌ Failed to initialize database")
            return False
            
        if not create_tables():
            logger.error("❌ Failed to create database tables")
            return False
            
        logger.info("✅ Database initialized successfully")
        
        # Check if we need initial scan
        scanner = get_initial_scanner()
        last_scan = await scanner.get_last_scan_summary()
        
        if not last_scan or last_scan.get('needs_refresh', True):
            logger.info("🔍 Performing initial asset scan...")
            result = await scanner.scan_all_assets(
                force_refresh=True,
                max_assets=int(os.getenv("MAX_ASSETS_TO_SCAN", "1500"))
            )
            
            summary = result.get_summary()
            logger.info(f"✅ Initial scan completed: {summary['valid_assets_count']} valid assets")
        else:
            logger.info(f"✅ Found {last_scan['valid_assets_count']} valid assets from previous scan")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ System initialization failed: {e}")
        return False


async def run_scanner():
    """Run the enhanced scanner worker."""
    try:
        # Initialize system first
        if not await initialize_system():
            logger.error("System initialization failed, exiting...")
            sys.exit(1)
        
        # Get configuration from environment
        use_parallel = os.getenv("USE_PARALLEL_SCANNER", "true").lower() == "true"
        
        logger.info(f"⚡ Starting Enhanced Scanner (Parallel Mode: {use_parallel})")
        
        # Create and run worker
        worker = EnhancedScannerWorker(use_parallel=use_parallel)
        
        if not await worker.initialize():
            logger.error("Failed to initialize scanner worker")
            sys.exit(1)
            
        # Log startup information
        logger.info(f"""
        🎯 Scanner Configuration:
        ├─ Parallel Mode: {use_parallel}
        ├─ Scan Interval: {os.getenv('SCAN_INTERVAL', '10')}s
        ├─ Max Assets: {os.getenv('MAX_ASSETS_TO_SCAN', '1500')}
        ├─ Environment: {os.getenv('ENVIRONMENT', 'production')}
        └─ Started at: {datetime.utcnow().isoformat()}
        """)
        
        # Run worker
        await worker.run()
        
    except KeyboardInterrupt:
        logger.info("👋 Received shutdown signal")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        logger.info("👋 Scanner shutdown complete")


def main():
    """Main entry point."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the scanner
    asyncio.run(run_scanner())


if __name__ == "__main__":
    main()