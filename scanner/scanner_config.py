# scanner/scanner_config.py
"""Configuration management for scanner operations."""

from dataclasses import dataclass, field
from typing import Dict, Any
import os


@dataclass
class ScannerConfig:
    """Configuration for scanner operations with sensible defaults."""
    
    # Performance settings
    max_concurrent_validations: int = 50  # Reduced from 100 for better stability
    batch_size: int = 20  # Size of each validation batch
    max_retries: int = 3  # Maximum retries for failed validations
    retry_delay: float = 1.0  # Delay between retries in seconds
    
    # Progress reporting
    progress_report_interval: int = 50  # Report progress every N processed items
    broadcast_progress_steps: int = 5  # Number of major progress steps
    
    # Database operations
    db_batch_size: int = 100  # Batch size for database operations
    commit_frequency: int = 50  # Commit every N operations
    
    # Cache settings
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600  # 1 hour
    
    # Validation settings
    validation_timeout_seconds: float = 30.0  # Timeout per validation
    enable_priority_processing: bool = True
    
    # Resource limits
    memory_limit_mb: int = 512  # Memory usage limit
    cpu_limit_percent: int = 80  # CPU usage limit
    
    # Error handling
    max_consecutive_errors: int = 10  # Stop if too many consecutive errors
    error_reporting_interval: int = 100  # Report errors every N items
    
    @classmethod
    def from_env(cls) -> 'ScannerConfig':
        """Create configuration from environment variables."""
        return cls(
            max_concurrent_validations=int(os.getenv('SCANNER_MAX_CONCURRENT', '50')),
            batch_size=int(os.getenv('SCANNER_BATCH_SIZE', '20')),
            max_retries=int(os.getenv('SCANNER_MAX_RETRIES', '3')),
            retry_delay=float(os.getenv('SCANNER_RETRY_DELAY', '1.0')),
            progress_report_interval=int(os.getenv('SCANNER_PROGRESS_INTERVAL', '50')),
            db_batch_size=int(os.getenv('SCANNER_DB_BATCH_SIZE', '100')),
            enable_caching=os.getenv('SCANNER_ENABLE_CACHE', 'true').lower() == 'true',
            cache_ttl_seconds=int(os.getenv('SCANNER_CACHE_TTL', '3600')),
            validation_timeout_seconds=float(os.getenv('SCANNER_VALIDATION_TIMEOUT', '30.0')),
            memory_limit_mb=int(os.getenv('SCANNER_MEMORY_LIMIT_MB', '512')),
            cpu_limit_percent=int(os.getenv('SCANNER_CPU_LIMIT_PERCENT', '80')),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'max_concurrent_validations': self.max_concurrent_validations,
            'batch_size': self.batch_size,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'progress_report_interval': self.progress_report_interval,
            'broadcast_progress_steps': self.broadcast_progress_steps,
            'db_batch_size': self.db_batch_size,
            'commit_frequency': self.commit_frequency,
            'enable_caching': self.enable_caching,
            'cache_ttl_seconds': self.cache_ttl_seconds,
            'validation_timeout_seconds': self.validation_timeout_seconds,
            'enable_priority_processing': self.enable_priority_processing,
            'memory_limit_mb': self.memory_limit_mb,
            'cpu_limit_percent': self.cpu_limit_percent,
            'max_consecutive_errors': self.max_consecutive_errors,
            'error_reporting_interval': self.error_reporting_interval,
        }
    
    def validate(self) -> None:
        """Validate configuration values."""
        if self.max_concurrent_validations <= 0:
            raise ValueError("max_concurrent_validations must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.retry_delay < 0:
            raise ValueError("retry_delay cannot be negative")
        if self.validation_timeout_seconds <= 0:
            raise ValueError("validation_timeout_seconds must be positive")
        if self.memory_limit_mb <= 0:
            raise ValueError("memory_limit_mb must be positive")
        if not 0 < self.cpu_limit_percent <= 100:
            raise ValueError("cpu_limit_percent must be between 1 and 100")


# Global configuration instance
_config: ScannerConfig = None


def get_scanner_config() -> ScannerConfig:
    """Get the global scanner configuration instance."""
    global _config
    if _config is None:
        _config = ScannerConfig.from_env()
        _config.validate()
    return _config


def set_scanner_config(config: ScannerConfig) -> None:
    """Set the global scanner configuration instance."""
    global _config
    config.validate()
    _config = config