#!/usr/bin/env python3
# utils/backup.py
"""Database backup utility for BingX Trading Bot."""

import asyncio
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


def create_database_backup():
    """Create a database backup using pg_dump."""
    try:
        # Get database URL from environment
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            logger.warning("DATABASE_URL not set, skipping backup")
            return False
        
        # Create backup filename with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"bingx_backup_{timestamp}.sql"
        
        # Create backups directory
        backups_dir = Path('backups')
        backups_dir.mkdir(exist_ok=True)
        backup_path = backups_dir / backup_filename
        
        logger.info(f"🗄️ Starting database backup to {backup_path}")
        
        # Run pg_dump
        cmd = [
            'pg_dump',
            database_url,
            '--no-password',
            '--verbose',
            '--clean',
            '--if-exists',
            '--file', str(backup_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes timeout
        )
        
        if result.returncode == 0:
            # Get backup file size
            backup_size = backup_path.stat().st_size
            logger.info(f"✅ Database backup completed successfully")
            logger.info(f"   - File: {backup_path}")
            logger.info(f"   - Size: {backup_size / 1024 / 1024:.2f} MB")
            
            # Clean up old backups (keep last 7 days)
            cleanup_old_backups(backups_dir, days_to_keep=7)
            return True
            
        else:
            logger.error(f"❌ Database backup failed")
            logger.error(f"   - Return code: {result.returncode}")
            logger.error(f"   - Error: {result.stderr}")
            return False
    
    except subprocess.TimeoutExpired:
        logger.error("❌ Database backup timed out")
        return False
    except Exception as e:
        logger.error(f"❌ Database backup error: {e}")
        return False


def cleanup_old_backups(backups_dir: Path, days_to_keep: int = 7):
    """Clean up old backup files."""
    try:
        cutoff_time = datetime.utcnow().timestamp() - (days_to_keep * 24 * 3600)
        
        deleted_count = 0
        for backup_file in backups_dir.glob("bingx_backup_*.sql"):
            if backup_file.stat().st_mtime < cutoff_time:
                backup_file.unlink()
                deleted_count += 1
                logger.info(f"🗑️ Deleted old backup: {backup_file.name}")
        
        if deleted_count > 0:
            logger.info(f"✅ Cleaned up {deleted_count} old backup files")
        
    except Exception as e:
        logger.warning(f"⚠️ Error cleaning up old backups: {e}")


def main():
    """Main backup function."""
    logger.info("🚀 Starting database backup job")
    
    try:
        create_database_backup()
        logger.info("✅ Backup job completed successfully")
    except Exception as e:
        logger.error(f"❌ Backup job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()