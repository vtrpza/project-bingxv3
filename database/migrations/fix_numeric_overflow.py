#!/usr/bin/env python3
"""
Database migration to fix numeric overflow issues in volume fields.
Increases precision from Numeric(20,8) to Numeric(30,8) for:
- indicators.volume_sma
- market_data.volume

This migration addresses the error:
psycopg2.errors.NumericValueOutOfRange: numeric field overflow
A field with precision 20, scale 8 must round to an absolute value less than 10^12.
"""

import sys
import os
import asyncio
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config.settings import get_database_url
from database.connection import DatabaseConnection
from utils.logger import setup_logger

logger = setup_logger("migration")

class NumericOverflowMigration:
    """Migration to fix numeric overflow in volume fields."""
    
    def __init__(self):
        self.database_url = get_database_url()
        
    def run_migration(self):
        """Execute the migration."""
        try:
            logger.info("Starting numeric overflow migration...")
            
            # Create engine
            engine = create_engine(self.database_url)
            
            with engine.connect() as conn:
                # Start transaction
                trans = conn.begin()
                
                try:
                    # Update indicators.volume_sma column
                    logger.info("Updating indicators.volume_sma column precision...")
                    conn.execute(text("""
                        ALTER TABLE indicators 
                        ALTER COLUMN volume_sma TYPE NUMERIC(30, 8)
                    """))
                    
                    # Update market_data.volume column
                    logger.info("Updating market_data.volume column precision...")
                    conn.execute(text("""
                        ALTER TABLE market_data 
                        ALTER COLUMN volume TYPE NUMERIC(30, 8)
                    """))
                    
                    # Commit transaction
                    trans.commit()
                    logger.info("Migration completed successfully!")
                    
                except Exception as e:
                    trans.rollback()
                    logger.error(f"Migration failed, rolling back: {e}")
                    raise
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error during migration: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during migration: {e}")
            raise
    
    def validate_migration(self):
        """Validate that the migration was successful."""
        try:
            logger.info("Validating migration...")
            
            # Create engine
            engine = create_engine(self.database_url)
            
            with engine.connect() as conn:
                # Check indicators table
                result = conn.execute(text("""
                    SELECT column_name, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_name = 'indicators' 
                    AND column_name = 'volume_sma'
                """))
                
                row = result.fetchone()
                if row and row[1] == 30 and row[2] == 8:
                    logger.info("✅ indicators.volume_sma column updated successfully")
                else:
                    logger.error(f"❌ indicators.volume_sma column validation failed: {row}")
                    return False
                
                # Check market_data table
                result = conn.execute(text("""
                    SELECT column_name, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_name = 'market_data' 
                    AND column_name = 'volume'
                """))
                
                row = result.fetchone()
                if row and row[1] == 30 and row[2] == 8:
                    logger.info("✅ market_data.volume column updated successfully")
                else:
                    logger.error(f"❌ market_data.volume column validation failed: {row}")
                    return False
                    
                logger.info("✅ Migration validation completed successfully!")
                return True
                
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False

def main():
    """Main migration function."""
    migration = NumericOverflowMigration()
    
    try:
        # Run the migration
        migration.run_migration()
        
        # Validate the migration
        if migration.validate_migration():
            logger.info("🎉 Migration completed and validated successfully!")
            print("✅ Migration completed successfully!")
            print("📊 Volume fields now support larger values (up to 10^22)")
            print("🔧 Database schema updated to prevent numeric overflow errors")
            return 0
        else:
            logger.error("❌ Migration validation failed!")
            print("❌ Migration validation failed!")
            return 1
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"❌ Migration failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)