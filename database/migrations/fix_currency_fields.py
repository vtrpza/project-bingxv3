#!/usr/bin/env python3
"""
Migration script to fix base_currency and quote_currency field sizes.
This fixes the issue with symbols like '1000000BABYDOGE' that exceed 10 characters.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try .env.dev
    env_path = project_root / '.env.dev'
    if env_path.exists():
        load_dotenv(env_path)

from database.connection import db_manager, init_database
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the migration to increase currency field sizes."""
    # Initialize database
    if not init_database():
        logger.error("Failed to initialize database")
        return False
        
    engine = db_manager.engine
    
    migration_queries = [
        # Increase base_currency field size
        """
        ALTER TABLE assets 
        ALTER COLUMN base_currency TYPE VARCHAR(20);
        """,
        
        # Increase quote_currency field size
        """
        ALTER TABLE assets 
        ALTER COLUMN quote_currency TYPE VARCHAR(20);
        """,
        
        # Add index for better performance
        """
        CREATE INDEX IF NOT EXISTS idx_assets_base_currency ON assets(base_currency);
        """,
        
        """
        CREATE INDEX IF NOT EXISTS idx_assets_quote_currency ON assets(quote_currency);
        """
    ]
    
    try:
        with engine.begin() as conn:
            for query in migration_queries:
                logger.info(f"Executing: {query.strip()}")
                conn.execute(text(query))
                logger.info("✅ Success")
        
        logger.info("🎉 Migration completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Starting database migration...")
    success = run_migration()
    sys.exit(0 if success else 1)