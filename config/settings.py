# config/settings.py
"""Main application settings and environment configuration."""

import os
import logging
from typing import Optional, List
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Application settings loaded from environment variables."""
    
    # Environment Configuration
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    VERSION: str = "3.0.0"
    
    # Application Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    LOGS_DIR: Path = BASE_DIR / "logs"
    
    # BingX API Configuration
    BINGX_API_KEY: Optional[str] = os.getenv("BINGX_API_KEY")
    BINGX_SECRET_KEY: Optional[str] = os.getenv("BINGX_SECRET_KEY")
    BINGX_TESTNET: bool = os.getenv("BINGX_TESTNET", "False").lower() == "true"
    BINGX_SANDBOX: bool = os.getenv("BINGX_SANDBOX", "False").lower() == "true"
    
    # Database Configuration
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "bingx_trading")
    DB_USER: str = os.getenv("DB_USER", "trading_bot")
    DB_PASSWORD: Optional[str] = os.getenv("DB_PASSWORD")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_ECHO: bool = os.getenv("DB_ECHO", "False").lower() == "true"
    
    # Redis Configuration (Optional)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "False").lower() == "true"
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "ERROR")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/trading_bot.log")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # Performance Configuration
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "4"))
    ENABLE_PROFILING: bool = os.getenv("ENABLE_PROFILING", "False").lower() == "true"
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    
    # Security Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # WebSocket Configuration
    WS_HOST: str = os.getenv("WS_HOST", "0.0.0.0")
    WS_PORT: int = int(os.getenv("WS_PORT", "8765"))
    WS_MAX_CONNECTIONS: int = int(os.getenv("WS_MAX_CONNECTIONS", "100"))
    
    # FastAPI Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_CORS_ORIGINS: List[str] = os.getenv("API_CORS_ORIGINS", "*").split(",")
    
    # Notification Configuration (Optional)
    TELEGRAM_BOT_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
    ENABLE_NOTIFICATIONS: bool = os.getenv("ENABLE_NOTIFICATIONS", "False").lower() == "true"
    
    # Render Deployment Configuration
    RENDER_SERVICE_ID: Optional[str] = os.getenv("RENDER_SERVICE_ID")
    IS_RENDER: bool = os.getenv("RENDER", "False").lower() == "true"
    
    @classmethod
    def validate(cls) -> List[str]:
        """Validate all required settings and return list of errors."""
        errors = []
        
        # Required API credentials
        if not cls.BINGX_API_KEY:
            errors.append("BINGX_API_KEY environment variable is required")
        
        if not cls.BINGX_SECRET_KEY:
            errors.append("BINGX_SECRET_KEY environment variable is required")
        
        # Database configuration
        if not cls.DATABASE_URL and not cls.DB_PASSWORD:
            errors.append("Either DATABASE_URL or DB_PASSWORD must be provided")
        
        # Validate numeric ranges
        if cls.DB_POOL_SIZE < 1:
            errors.append("DB_POOL_SIZE must be at least 1")
        
        if cls.MAX_WORKERS < 1:
            errors.append("MAX_WORKERS must be at least 1")
        
        if cls.REQUEST_TIMEOUT < 1:
            errors.append("REQUEST_TIMEOUT must be at least 1 second")
        
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if cls.LOG_LEVEL.upper() not in valid_log_levels:
            errors.append(f"LOG_LEVEL must be one of: {valid_log_levels}")
        
        return errors
    
    @classmethod
    def create_directories(cls):
        """Create required directories if they don't exist."""
        try:
            cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created logs directory: {cls.LOGS_DIR}")
        except Exception as e:
            logger.error(f"Failed to create logs directory: {e}")
    
    @classmethod
    def get_database_url(cls) -> str:
        """Get complete database URL."""
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        
        return (
            f"postgresql://{cls.DB_USER}:{cls.DB_PASSWORD}"
            f"@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
        )
    
    @classmethod
    def is_development(cls) -> bool:
        """Check if running in development environment."""
        return cls.ENVIRONMENT.lower() in ["development", "dev", "local"]
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production environment."""
        return cls.ENVIRONMENT.lower() in ["production", "prod"]
    
    @classmethod
    def is_testing(cls) -> bool:
        """Check if running in test environment."""
        return cls.ENVIRONMENT.lower() in ["testing", "test"]
    
    @classmethod
    def setup_logging(cls):
        """Setup application logging configuration."""
        cls.create_directories()
        
        # Configure root logger
        numeric_level = getattr(logging, cls.LOG_LEVEL.upper(), logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(cls.LOG_FORMAT)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        
        # File handler (with rotation)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            cls.LOG_FILE,
            maxBytes=cls.LOG_MAX_BYTES,
            backupCount=cls.LOG_BACKUP_COUNT
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        root_logger.handlers.clear()  # Clear existing handlers
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        
        # Reduce noise from external libraries
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("websockets").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        
        logger.info(f"Logging configured - Level: {cls.LOG_LEVEL}, File: {cls.LOG_FILE}")
    
    @classmethod
    def get_info(cls) -> dict:
        """Get application information."""
        return {
            "version": cls.VERSION,
            "environment": cls.ENVIRONMENT,
            "debug": cls.DEBUG,
            "testnet": cls.BINGX_TESTNET,
            "database_configured": bool(cls.DATABASE_URL or cls.DB_PASSWORD),
            "redis_enabled": cls.REDIS_ENABLED,
            "notifications_enabled": cls.ENABLE_NOTIFICATIONS,
        }


# Configuration validation on import
def validate_settings():
    """Validate settings on module import."""
    errors = Settings.validate()
    if errors:
        error_message = "Configuration validation failed:\n" + "\n".join(f"- {error}" for error in errors)
        logger.error(error_message)
        if Settings.is_production():
            raise ValueError(error_message)
        else:
            logger.warning("Running with invalid configuration (non-production environment)")


# Initialize logging
Settings.setup_logging()

# Global settings instance
_settings_instance = None


def get_settings() -> Settings:
    """Get global settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


# Validate settings
validate_settings()

logger.info(f"Settings loaded - Environment: {Settings.ENVIRONMENT}, Debug: {Settings.DEBUG}")