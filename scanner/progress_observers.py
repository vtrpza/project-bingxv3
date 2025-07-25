# scanner/progress_observers.py
"""Observer pattern implementation for scanner progress reporting."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import logging

from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    """Represents a progress event during scanning."""
    
    event_type: str  # 'started', 'progress', 'completed', 'error', 'step'
    message: str
    current_step: int = 0
    total_steps: int = 0
    processed_count: int = 0
    total_count: int = 0
    progress_percentage: float = 0.0
    timestamp: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = utc_now()
        if self.metadata is None:
            self.metadata = {}
        
        # Calculate progress percentage if not provided
        if self.progress_percentage == 0.0 and self.total_count > 0:
            self.progress_percentage = (self.processed_count / self.total_count) * 100.0


class ProgressObserver(ABC):
    """Abstract base class for progress observers."""
    
    @abstractmethod
    async def on_progress_update(self, event: ProgressEvent) -> None:
        """Handle progress update event."""
        pass
    
    @abstractmethod
    async def on_scan_started(self, event: ProgressEvent) -> None:
        """Handle scan started event."""
        pass
    
    @abstractmethod
    async def on_scan_completed(self, event: ProgressEvent) -> None:
        """Handle scan completed event."""
        pass
    
    @abstractmethod
    async def on_scan_error(self, event: ProgressEvent) -> None:
        """Handle scan error event."""
        pass


class WebSocketProgressObserver(ProgressObserver):
    """Progress observer that broadcasts updates via WebSocket."""
    
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
    
    async def on_progress_update(self, event: ProgressEvent) -> None:
        """Broadcast progress update via WebSocket."""
        try:
            message = {
                "type": "scanner_progress",
                "payload": {
                    "message": event.message,
                    "current_step": event.current_step,
                    "total_steps": event.total_steps,
                    "processed_count": event.processed_count,
                    "total_assets": event.total_count,
                    "progress_percentage": event.progress_percentage,
                    "timestamp": event.timestamp.isoformat(),
                    "status": "validating",
                    **event.metadata
                }
            }
            await self.connection_manager.broadcast(message)
        except Exception as e:
            logger.warning(f"Failed to broadcast progress update: {e}")
    
    async def on_scan_started(self, event: ProgressEvent) -> None:
        """Broadcast scan started event."""
        try:
            message = {
                "type": "scanner_started",
                "payload": {
                    "message": event.message,
                    "total_assets": event.total_count,
                    "timestamp": event.timestamp.isoformat(),
                    "status": "started",
                    **event.metadata
                }
            }
            await self.connection_manager.broadcast(message)
        except Exception as e:
            logger.warning(f"Failed to broadcast scan started: {e}")
    
    async def on_scan_completed(self, event: ProgressEvent) -> None:
        """Broadcast scan completed event."""
        try:
            message = {
                "type": "scanner_completion",
                "payload": {
                    "message": event.message,
                    "total_assets": event.total_count,
                    "processed_count": event.processed_count,
                    "timestamp": event.timestamp.isoformat(),
                    "status": "completed",
                    **event.metadata
                }
            }
            await self.connection_manager.broadcast(message)
        except Exception as e:
            logger.warning(f"Failed to broadcast scan completion: {e}")
    
    async def on_scan_error(self, event: ProgressEvent) -> None:
        """Broadcast scan error event."""
        try:
            message = {
                "type": "scanner_error",
                "payload": {
                    "message": event.message,
                    "timestamp": event.timestamp.isoformat(),
                    "status": "error",
                    **event.metadata
                }
            }
            await self.connection_manager.broadcast(message)
        except Exception as e:
            logger.warning(f"Failed to broadcast scan error: {e}")


class LoggingProgressObserver(ProgressObserver):
    """Progress observer that logs updates."""
    
    def __init__(self, logger_instance: Optional[logging.Logger] = None):
        self.logger = logger_instance or logger
    
    async def on_progress_update(self, event: ProgressEvent) -> None:
        """Log progress update."""
        if event.processed_count % 50 == 0 or event.progress_percentage >= 100:
            self.logger.info(
                f"Progress: {event.processed_count}/{event.total_count} "
                f"({event.progress_percentage:.1f}%) - {event.message}"
            )
    
    async def on_scan_started(self, event: ProgressEvent) -> None:
        """Log scan started."""
        self.logger.info(f"Scanner started: {event.message} ({event.total_count} assets)")
    
    async def on_scan_completed(self, event: ProgressEvent) -> None:
        """Log scan completion."""
        self.logger.info(
            f"Scanner completed: {event.message} "
            f"({event.processed_count}/{event.total_count} processed) "
            f"in {event.metadata.get('duration_seconds', 'unknown')}s"
        )
    
    async def on_scan_error(self, event: ProgressEvent) -> None:
        """Log scan error."""
        self.logger.error(f"Scanner error: {event.message}")


class CompositeProgressObserver(ProgressObserver):
    """Progress observer that delegates to multiple observers."""
    
    def __init__(self, observers: List[ProgressObserver] = None):
        self.observers = observers or []
    
    def add_observer(self, observer: ProgressObserver) -> None:
        """Add a progress observer."""
        self.observers.append(observer)
    
    def remove_observer(self, observer: ProgressObserver) -> None:
        """Remove a progress observer."""
        if observer in self.observers:
            self.observers.remove(observer)
    
    async def on_progress_update(self, event: ProgressEvent) -> None:
        """Notify all observers of progress update."""
        for observer in self.observers:
            try:
                await observer.on_progress_update(event)
            except Exception as e:
                logger.warning(f"Observer {type(observer).__name__} failed on progress update: {e}")
    
    async def on_scan_started(self, event: ProgressEvent) -> None:
        """Notify all observers of scan start."""
        for observer in self.observers:
            try:
                await observer.on_scan_started(event)
            except Exception as e:
                logger.warning(f"Observer {type(observer).__name__} failed on scan started: {e}")
    
    async def on_scan_completed(self, event: ProgressEvent) -> None:
        """Notify all observers of scan completion."""
        for observer in self.observers:
            try:
                await observer.on_scan_completed(event)
            except Exception as e:
                logger.warning(f"Observer {type(observer).__name__} failed on scan completed: {e}")
    
    async def on_scan_error(self, event: ProgressEvent) -> None:
        """Notify all observers of scan error."""
        for observer in self.observers:
            try:
                await observer.on_scan_error(event)
            except Exception as e:
                logger.warning(f"Observer {type(observer).__name__} failed on scan error: {e}")


class ProgressReporter:
    """Central progress reporter that manages observers."""
    
    def __init__(self, observer: ProgressObserver = None):
        self.observer = observer or CompositeProgressObserver()
    
    def set_observer(self, observer: ProgressObserver) -> None:
        """Set the progress observer."""
        self.observer = observer
    
    async def report_progress(self, event: ProgressEvent) -> None:
        """Report a progress event."""
        if event.event_type == 'started':
            await self.observer.on_scan_started(event)
        elif event.event_type == 'progress':
            await self.observer.on_progress_update(event)
        elif event.event_type == 'completed':
            await self.observer.on_scan_completed(event)
        elif event.event_type == 'error':
            await self.observer.on_scan_error(event)
        else:
            # Default to progress update for unknown types
            await self.observer.on_progress_update(event)
    
    async def report_started(self, message: str, total_count: int = 0, **metadata) -> None:
        """Report scan started."""
        event = ProgressEvent(
            event_type='started',
            message=message,
            total_count=total_count,
            metadata=metadata
        )
        await self.report_progress(event)
    
    async def report_step_progress(self, message: str, current_step: int, total_steps: int, **metadata) -> None:
        """Report step progress."""
        event = ProgressEvent(
            event_type='progress',
            message=message,
            current_step=current_step,
            total_steps=total_steps,
            progress_percentage=(current_step / total_steps) * 100.0 if total_steps > 0 else 0.0,
            metadata=metadata
        )
        await self.report_progress(event)
    
    async def report_item_progress(self, message: str, processed: int, total: int, **metadata) -> None:
        """Report item-by-item progress."""
        event = ProgressEvent(
            event_type='progress',
            message=message,
            processed_count=processed,
            total_count=total,
            metadata=metadata
        )
        await self.report_progress(event)
    
    async def report_completed(self, message: str, processed: int = 0, total: int = 0, **metadata) -> None:
        """Report scan completion."""
        event = ProgressEvent(
            event_type='completed',
            message=message,
            processed_count=processed,
            total_count=total,
            progress_percentage=100.0,
            metadata=metadata
        )
        await self.report_progress(event)
    
    async def report_error(self, message: str, **metadata) -> None:
        """Report scan error."""
        event = ProgressEvent(
            event_type='error',
            message=message,
            metadata=metadata
        )
        await self.report_progress(event)