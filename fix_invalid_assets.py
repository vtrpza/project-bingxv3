#!/usr/bin/env python3
"""
Script to mark invalid assets as inactive in the database.
This will prevent them from being processed in the live-data endpoint.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection import get_session, init_database
from database.models import Asset
from utils.datetime_utils import utc_now
from utils.logger import get_logger

logger = get_logger(__name__)

def main():
    """Mark known invalid assets as inactive."""
    
    # Initialize database
    try:
        init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False
    
    # List of assets that are causing "Error processing asset: 4"
    invalid_assets = [
        'ANIME/USDT',
        'ANKR/USDT', 
        'ANT/USDT',
        'ANTT/USDT'
    ]
    
    updated_count = 0
    not_found_count = 0
    
    try:
        with get_session() as session:
            for symbol in invalid_assets:
                logger.info(f"Processing asset: {symbol}")
                
                # Find the asset
                asset = session.query(Asset).filter(Asset.symbol == symbol).first()
                
                if asset:
                    if asset.is_valid:
                        # Mark as invalid
                        asset.is_valid = False
                        asset.last_validation = utc_now()
                        asset.validation_data = {
                            "error": "symbol_not_found_on_bingx",
                            "timestamp": utc_now().isoformat(),
                            "fixed_by": "fix_invalid_assets_script"
                        }
                        updated_count += 1
                        logger.info(f"✅ Marked {symbol} as invalid")
                    else:
                        logger.info(f"ℹ️  {symbol} already marked as invalid")
                else:
                    not_found_count += 1
                    logger.warning(f"❌ Asset {symbol} not found in database")
            
            # Commit all changes
            session.commit()
            logger.info(f"✅ Database changes committed successfully")
            
    except Exception as e:
        logger.error(f"❌ Error updating assets: {e}")
        return False
    
    # Summary
    logger.info(f"""
📊 SUMMARY:
- Assets processed: {len(invalid_assets)}
- Assets updated: {updated_count}
- Assets not found: {not_found_count}
- Status: {'SUCCESS' if updated_count > 0 or not_found_count == len(invalid_assets) else 'PARTIAL'}
    """)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)