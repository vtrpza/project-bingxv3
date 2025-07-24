# database/connection.py
"""Database connection management for BingX Trading Bot."""

import os
import logging
from typing import Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError

from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
        self.is_sqlite = False
    
    def initialize(self) -> bool:
        """Initialize database connection."""
        try:
            # Check if DATABASE_URL is provided (Render/Heroku style)
            database_url = os.getenv("DATABASE_URL")
            
            if not database_url:
                # Fallback to SQLite for easy local development
                logger.info("No DATABASE_URL found, using SQLite for local development")
                database_url = "sqlite:///vst_trading.db"
            else:
                logger.info("Using DATABASE_URL from environment")
            
            # Handle SQLite vs PostgreSQL differences
            if database_url.startswith("sqlite"):
                self.is_sqlite = True
                logger.info("Using SQLite database")
            else:
                self.is_sqlite = False
                logger.info("Using PostgreSQL database")
            
            # Create engine with appropriate configuration
            if self.is_sqlite:
                # SQLite configuration (simple, no pooling needed)
                self.engine = create_engine(
                    database_url,
                    echo=os.getenv("DB_ECHO", "false").lower() == "true",
                    future=True
                )
            else:
                # PostgreSQL configuration (with connection pooling)
                self.engine = create_engine(
                    database_url,
                    poolclass=QueuePool,
                    pool_size=20,
                    max_overflow=40,
                    pool_timeout=30,
                    pool_recycle=3600,
                    echo=os.getenv("DB_ECHO", "false").lower() == "true",
                    future=True
                )
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False
            )
            
            # Test connection
            with self.engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(text("SELECT 1"))
                logger.info("Database connection established successfully")
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False
    
    def create_tables(self) -> bool:
        """Create all database tables."""
        try:
            if not self._initialized:
                raise RuntimeError("Database not initialized")
                
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            return False
    
    def drop_tables(self) -> bool:
        """Drop all database tables (use with caution)."""
        try:
            if not self._initialized:
                raise RuntimeError("Database not initialized")
                
            Base.metadata.drop_all(bind=self.engine)
            logger.warning("All database tables dropped")
            return True
            
        except Exception as e:
            logger.error(f"Failed to drop tables: {e}")
            return False
    
    @contextmanager
    def get_session(self):
        """Get database session with automatic cleanup."""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
            
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error in database session: {e}")
            raise
        finally:
            session.close()
    
    def get_session_factory(self) -> sessionmaker:
        """Get session factory for advanced usage."""
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        return self.SessionLocal
    
    def health_check(self) -> bool:
        """Check database connection health."""
        try:
            if not self._initialized:
                return False
                
            with self.engine.connect() as conn:
                from sqlalchemy import text
                result = conn.execute(text("SELECT 1")).scalar()
                return result == 1
                
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def close(self):
        """Close database connections."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


def init_database() -> bool:
    """Initialize the global database manager."""
    return db_manager.initialize()


def create_tables() -> bool:
    """Create all database tables."""
    return db_manager.create_tables()


def get_db_session():
    """Dependency function to get database session (for FastAPI)."""
    with db_manager.get_session() as session:
        yield session


def get_db():
    """Alias for get_db_session for compatibility."""
    return get_db_session()


@contextmanager
def get_session():
    """Context manager for database sessions."""
    if not db_manager._initialized:
        raise RuntimeError("Database not initialized - call init_database() first")
    with db_manager.get_session() as session:
        yield session


def health_check() -> bool:
    """Check database health."""
    return db_manager.health_check()


def close_database():
    """Close database connections."""
    db_manager.close()