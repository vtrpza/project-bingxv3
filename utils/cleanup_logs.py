#!/usr/bin/env python3
# utils/cleanup_logs.py
"""Log cleanup utility for BingX Trading Bot."""

import os
import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


def cleanup_log_files():
    """Clean up old log files."""
    try:
        # Get retention period from environment (default 30 days)
        retention_days = int(os.getenv('LOG_RETENTION_DAYS', '30'))
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        logger.info(f"🧹 Starting log cleanup (keeping {retention_days} days)")
        logger.info(f"   - Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get logs directory
        logs_dir = Path(Settings.LOGS_DIR)
        
        if not logs_dir.exists():
            logger.info("📁 Logs directory does not exist, nothing to clean")
            return
        
        deleted_files = 0
        deleted_size = 0
        
        # Clean up log files
        for log_file in logs_dir.glob("*.log*"):
            try:
                # Check file modification time
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                
                if file_mtime < cutoff_date:
                    file_size = log_file.stat().st_size
                    log_file.unlink()
                    deleted_files += 1
                    deleted_size += file_size
                    logger.info(f"🗑️ Deleted old log: {log_file.name} "
                              f"({file_size / 1024:.1f} KB, modified: {file_mtime.strftime('%Y-%m-%d')})")
            
            except Exception as e:
                logger.warning(f"⚠️ Error processing {log_file}: {e}")
        
        # Clean up empty directories
        try:
            for item in logs_dir.iterdir():
                if item.is_dir() and not any(item.iterdir()):
                    item.rmdir()
                    logger.info(f"🗑️ Removed empty directory: {item.name}")
        except Exception as e:
            logger.warning(f"⚠️ Error cleaning directories: {e}")
        
        # Summary
        if deleted_files > 0:
            logger.info(f"✅ Log cleanup completed:")
            logger.info(f"   - Files deleted: {deleted_files}")
            logger.info(f"   - Space freed: {deleted_size / 1024 / 1024:.2f} MB")
        else:
            logger.info("✅ No old log files found to delete")
    
    except Exception as e:
        logger.error(f"❌ Log cleanup error: {e}")
        sys.exit(1)


def cleanup_temp_files():
    """Clean up temporary files."""
    try:
        temp_patterns = [
            "*.tmp",
            "*.temp", 
            "__pycache__",
            "*.pyc",
            ".pytest_cache"
        ]
        
        deleted_count = 0
        
        for pattern in temp_patterns:
            for temp_file in Path.cwd().rglob(pattern):
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                        deleted_count += 1
                    elif temp_file.is_dir():
                        shutil.rmtree(temp_file)
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Could not delete {temp_file}: {e}")
        
        if deleted_count > 0:
            logger.info(f"🧹 Cleaned up {deleted_count} temporary files/directories")
    
    except Exception as e:
        logger.warning(f"⚠️ Error cleaning temporary files: {e}")


def get_disk_usage():
    """Get current disk usage information."""
    try:
        logs_dir = Path(Settings.LOGS_DIR)
        if logs_dir.exists():
            total_size = sum(f.stat().st_size for f in logs_dir.rglob('*') if f.is_file())
            file_count = len(list(logs_dir.rglob('*.log*')))
            
            logger.info(f"📊 Current logs directory stats:")
            logger.info(f"   - Total size: {total_size / 1024 / 1024:.2f} MB")
            logger.info(f"   - Log files: {file_count}")
    
    except Exception as e:
        logger.warning(f"⚠️ Error getting disk usage: {e}")


def main():
    """Main cleanup function."""
    logger.info("🚀 Starting log cleanup job")
    
    try:
        # Show current usage
        get_disk_usage()
        
        # Clean up log files
        cleanup_log_files()
        
        # Clean up temporary files
        cleanup_temp_files()
        
        # Show final usage
        get_disk_usage()
        
        logger.info("✅ Log cleanup job completed successfully")
    
    except Exception as e:
        logger.error(f"❌ Log cleanup job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()