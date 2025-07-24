# utils/logger.py
"""Advanced logging utilities for BingX Trading Bot."""

import logging
import logging.handlers
import json
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from config.settings import Settings


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging with JSON output."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured data."""
        # Base log structure
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception information if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                          'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process', 'getMessage',
                          'message'}:
                log_data[key] = value
        
        return json.dumps(log_data, default=str)


class TradingLogger:
    """Specialized logger for trading operations."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup specialized handlers for trading logs."""
        # Trading-specific file handler
        trading_log_file = Settings.LOGS_DIR / "trading.log"
        trading_handler = logging.handlers.RotatingFileHandler(
            trading_log_file,
            maxBytes=Settings.LOG_MAX_BYTES,
            backupCount=Settings.LOG_BACKUP_COUNT
        )
        trading_handler.setFormatter(StructuredFormatter())
        trading_handler.setLevel(logging.INFO)
        
        # Error-specific file handler
        error_log_file = Settings.LOGS_DIR / "errors.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=Settings.LOG_MAX_BYTES,
            backupCount=Settings.LOG_BACKUP_COUNT
        )
        error_handler.setFormatter(StructuredFormatter())
        error_handler.setLevel(logging.ERROR)
        
        self.logger.addHandler(trading_handler)
        self.logger.addHandler(error_handler)
    
    def trade_opened(self, symbol: str, side: str, quantity: float, price: float, 
                    trade_id: str, reason: str = None, **kwargs):
        """Log trade opening event."""
        self.logger.info(
            "Trade opened",
            extra={
                "event_type": "trade_opened",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "trade_id": trade_id,
                "reason": reason,
                **kwargs
            }
        )
    
    def trade_closed(self, symbol: str, trade_id: str, exit_price: float, 
                    pnl: float, reason: str = None, **kwargs):
        """Log trade closing event."""
        self.logger.info(
            "Trade closed",
            extra={
                "event_type": "trade_closed",
                "symbol": symbol,
                "trade_id": trade_id,
                "exit_price": exit_price,
                "pnl": pnl,
                "reason": reason,
                **kwargs
            }
        )
    
    def signal_generated(self, symbol: str, signal_type: str, strength: float,
                        rules: list, indicators: dict, **kwargs):
        """Log signal generation event."""
        self.logger.info(
            "Signal generated",
            extra={
                "event_type": "signal_generated",
                "symbol": symbol,
                "signal_type": signal_type,
                "strength": strength,
                "rules_triggered": rules,
                "indicators": indicators,
                **kwargs
            }
        )
    
    def order_executed(self, symbol: str, order_type: str, side: str, 
                      quantity: float, price: float, order_id: str, **kwargs):
        """Log order execution event."""
        self.logger.info(
            "Order executed",
            extra={
                "event_type": "order_executed",
                "symbol": symbol,
                "order_type": order_type,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_id": order_id,
                **kwargs
            }
        )
    
    def risk_event(self, event_type: str, symbol: str, details: dict, **kwargs):
        """Log risk management events."""
        self.logger.warning(
            f"Risk event: {event_type}",
            extra={
                "event_type": "risk_event",
                "risk_type": event_type,
                "symbol": symbol,
                "details": details,
                **kwargs
            }
        )
    
    def error_event(self, error_type: str, message: str, details: dict = None, **kwargs):
        """Log error events."""
        self.logger.error(
            f"Error: {error_type} - {message}",
            extra={
                "event_type": "error",
                "error_type": error_type,
                "details": details or {},
                **kwargs
            }
        )


class PerformanceLogger:
    """Logger for performance monitoring and profiling."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(f"{name}.performance")
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup performance-specific handlers."""
        perf_log_file = Settings.LOGS_DIR / "performance.log"
        perf_handler = logging.handlers.RotatingFileHandler(
            perf_log_file,
            maxBytes=Settings.LOG_MAX_BYTES,
            backupCount=Settings.LOG_BACKUP_COUNT
        )
        perf_handler.setFormatter(StructuredFormatter())
        perf_handler.setLevel(logging.INFO)
        
        self.logger.addHandler(perf_handler)
    
    def execution_time(self, operation: str, duration: float, details: dict = None):
        """Log operation execution time."""
        self.logger.info(
            f"Operation timing: {operation}",
            extra={
                "event_type": "performance",
                "operation": operation,
                "duration_seconds": duration,
                "details": details or {}
            }
        )
    
    def api_request(self, endpoint: str, method: str, duration: float, 
                   status_code: int = None, error: str = None):
        """Log API request performance."""
        self.logger.info(
            f"API request: {method} {endpoint}",
            extra={
                "event_type": "api_request",
                "endpoint": endpoint,
                "method": method,
                "duration_seconds": duration,
                "status_code": status_code,
                "error": error
            }
        )
    
    def database_query(self, query_type: str, table: str, duration: float, 
                      rows_affected: int = None):
        """Log database query performance."""
        self.logger.info(
            f"Database query: {query_type} on {table}",
            extra={
                "event_type": "database_query",
                "query_type": query_type,
                "table": table,
                "duration_seconds": duration,
                "rows_affected": rows_affected
            }
        )


def get_logger(name: str, logger_type: str = "standard") -> logging.Logger:
    """Get appropriate logger instance."""
    if logger_type == "trading":
        return TradingLogger(name).logger
    elif logger_type == "performance":
        return PerformanceLogger(name).logger
    else:
        return logging.getLogger(name)


def log_function_call(func):
    """Decorator to log function calls and execution time."""
    import functools
    import time
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        start_time = time.time()
        
        try:
            logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"Completed {func.__name__} in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error in {func.__name__} after {execution_time:.3f}s: {e}")
            raise
    
    return wrapper


def setup_module_logger(module_name: str, level: str = None) -> logging.Logger:
    """Setup logger for a specific module."""
    logger = logging.getLogger(module_name)
    
    if level:
        numeric_level = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(numeric_level)
    
    return logger


# Create common loggers
trading_logger = TradingLogger("trading")
performance_logger = PerformanceLogger("performance")