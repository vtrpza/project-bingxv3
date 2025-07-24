#!/usr/bin/env python3
# utils/maintenance_worker.py
"""Background maintenance worker for BingX Trading Bot."""

import asyncio
import os
import sys
import signal
from datetime import datetime, time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import get_logger
from utils.backup import create_database_backup
from utils.cleanup_logs import cleanup_log_files, cleanup_temp_files

logger = get_logger(__name__)


class MaintenanceWorker:
    """Background worker for maintenance tasks."""
    
    def __init__(self):
        self.is_running = False
        self.tasks = {}
        
        # Maintenance schedule (UTC times)
        self.schedule = {
            'daily_backup': time(2, 0),      # 2:00 AM UTC
            'log_cleanup': time(3, 0),       # 3:00 AM UTC (daily)
            'temp_cleanup': time(1, 0),      # 1:00 AM UTC (daily)
        }
        
        # Track last execution
        self.last_execution = {}
    
    async def start(self):
        """Start the maintenance worker."""
        if self.is_running:
            logger.warning("Maintenance worker is already running")
            return
        
        logger.info("🚀 Starting maintenance worker")
        self.is_running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        try:
            await self._run_maintenance_loop()
        except Exception as e:
            logger.error(f"❌ Maintenance worker error: {e}")
        finally:
            self.is_running = False
            logger.info("🛑 Maintenance worker stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("📡 Received shutdown signal")
        self.is_running = False
    
    async def _run_maintenance_loop(self):
        """Main maintenance loop."""
        logger.info("🔄 Starting maintenance loop")
        
        while self.is_running:
            try:
                current_time = datetime.utcnow().time()
                current_date = datetime.utcnow().date()
                
                # Check each scheduled task
                for task_name, scheduled_time in self.schedule.items():
                    # Check if it's time to run this task
                    if self._should_run_task(task_name, current_time, current_date):
                        logger.info(f"⏰ Running scheduled task: {task_name}")
                        
                        try:
                            await self._run_task(task_name)
                            self.last_execution[task_name] = current_date
                            logger.info(f"✅ Task completed: {task_name}")
                        except Exception as e:
                            logger.error(f"❌ Task failed: {task_name} - {e}")
                
                # Sleep for 1 minute before next check
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in maintenance loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    def _should_run_task(self, task_name: str, current_time: time, current_date) -> bool:
        """Check if a task should run now."""
        scheduled_time = self.schedule[task_name]
        last_run = self.last_execution.get(task_name)
        
        # Check if we're within 1 minute of scheduled time
        current_minutes = current_time.hour * 60 + current_time.minute
        scheduled_minutes = scheduled_time.hour * 60 + scheduled_time.minute
        
        # Allow 1 minute window
        time_match = abs(current_minutes - scheduled_minutes) <= 1
        
        # Check if we haven't run today
        not_run_today = last_run != current_date
        
        return time_match and not_run_today
    
    async def _run_task(self, task_name: str):
        """Execute a maintenance task."""
        if task_name == 'daily_backup':
            await self._run_daily_backup()
        elif task_name == 'log_cleanup':
            await self._run_log_cleanup()
        elif task_name == 'temp_cleanup':
            await self._run_temp_cleanup()
        else:
            logger.warning(f"Unknown task: {task_name}")
    
    async def _run_daily_backup(self):
        """Run daily database backup."""
        try:
            # Run backup in executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, create_database_backup)
        except Exception as e:
            logger.error(f"Backup task error: {e}")
            raise
    
    async def _run_log_cleanup(self):
        """Run log cleanup."""
        try:
            # Run cleanup in executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, cleanup_log_files)
        except Exception as e:
            logger.error(f"Log cleanup task error: {e}")
            raise
    
    async def _run_temp_cleanup(self):
        """Run temporary files cleanup."""
        try:
            # Run cleanup in executor to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, cleanup_temp_files)
        except Exception as e:
            logger.error(f"Temp cleanup task error: {e}")
            raise
    
    async def get_status(self) -> dict:
        """Get maintenance worker status."""
        return {
            'running': self.is_running,
            'schedule': {name: time.strftime('%H:%M UTC') for name, time in self.schedule.items()},
            'last_execution': {name: date.isoformat() for name, date in self.last_execution.items()},
            'next_tasks': self._get_next_tasks()
        }
    
    def _get_next_tasks(self) -> dict:
        """Get next scheduled tasks."""
        current_time = datetime.utcnow()
        next_tasks = {}
        
        for task_name, scheduled_time in self.schedule.items():
            # Calculate next run time
            next_run = datetime.combine(current_time.date(), scheduled_time)
            if next_run <= current_time:
                # Task is for tomorrow
                next_run = next_run.replace(day=next_run.day + 1)
            
            next_tasks[task_name] = next_run.isoformat()
        
        return next_tasks


async def main():
    """Main entry point."""
    logger.info("🤖 BingX Trading Bot - Maintenance Worker")
    
    worker = MaintenanceWorker()
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("👋 Maintenance worker interrupted")
    except Exception as e:
        logger.error(f"❌ Maintenance worker error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Create logs directory
    os.makedirs('logs', exist_ok=True)
    
    # Run the maintenance worker
    asyncio.run(main())