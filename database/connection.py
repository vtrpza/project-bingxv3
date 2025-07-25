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
                # PostgreSQL configuration optimized for Render
                self.engine = create_engine(
                    database_url,
                    poolclass=QueuePool,
                    pool_size=10,      # Increased from 5 to handle background tasks
                    max_overflow=20,   # Increased from 10 for peak loads
                    pool_timeout=30,   # Reduced from 60 to fail faster
                    pool_recycle=1800, # Reduced from 3600 to recycle connections more frequently
                    pool_pre_ping=True,  # Test connections before use
                    connect_args={
                        "connect_timeout": 10,  # Reduced from 30 for faster failure
                        "application_name": "bingx_trading_bot",
                        "keepalives": 1,
                        "keepalives_idle": 30,
                        "keepalives_interval": 10,
                        "keepalives_count": 5
                    },
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
        import time
        from sqlalchemy.exc import OperationalError
        from sqlalchemy import text
        
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                if not self._initialized:
                    raise RuntimeError("Database not initialized")
                
                # Use a transaction with explicit lock to prevent concurrent creates
                with self.engine.begin() as conn:
                    # Try to acquire an advisory lock to prevent concurrent creates
                    # This is PostgreSQL specific
                    try:
                        conn.execute(text("SELECT pg_advisory_lock(12346)"))
                        Base.metadata.create_all(bind=conn)
                        conn.execute(text("SELECT pg_advisory_unlock(12346)"))
                    except Exception:
                        # If advisory locks fail, just try to create tables
                        Base.metadata.create_all(bind=conn)
                
                logger.info("Database tables created successfully")
                return True
                
            except OperationalError as e:
                if "deadlock detected" in str(e).lower() and attempt < max_retries - 1:
                    logger.warning(f"Deadlock detected on attempt {attempt + 1}, retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(f"Failed to create tables after {attempt + 1} attempts: {e}")
                    return False
            except Exception as e:
                logger.error(f"Failed to create tables: {e}")
                return False
        
        return False
    
    def drop_tables(self) -> bool:
        """Drop all database tables (use with caution)."""
        import time
        from sqlalchemy.exc import OperationalError, StatementError
        from sqlalchemy import text
        
        max_retries = 3
        retry_delay = 1  # Start with 1 second
        
        for attempt in range(max_retries):
            try:
                if not self._initialized:
                    raise RuntimeError("Database not initialized")
                
                # First, try to terminate all connections to prevent locks
                try:
                    with self.engine.connect() as conn:
                        # Get database name from connection URL
                        db_name_result = conn.execute(text("SELECT current_database()"))
                        db_name = db_name_result.scalar()
                        
                        # Terminate other connections to the database (PostgreSQL specific)
                        conn.execute(text(f"""
                            SELECT pg_terminate_backend(pg_stat_activity.pid)
                            FROM pg_stat_activity
                            WHERE pg_stat_activity.datname = '{db_name}'
                              AND pid <> pg_backend_pid()
                        """))
                        
                        logger.info("Terminated existing database connections")
                except Exception as e:
                    logger.warning(f"Could not terminate connections: {e}")
                
                # Now attempt to drop tables with transaction recovery
                connection = self.engine.connect()
                trans = connection.begin()
                
                try:
                    # Try to acquire an advisory lock to prevent concurrent drops
                    connection.execute(text("SELECT pg_advisory_lock(12345)"))
                    
                    # Drop all tables
                    Base.metadata.drop_all(bind=connection)
                    
                    # Release the lock
                    connection.execute(text("SELECT pg_advisory_unlock(12345)"))
                    
                    # Commit the transaction
                    trans.commit()
                    logger.warning("All database tables dropped successfully")
                    return True
                    
                except Exception as inner_e:
                    # Rollback the transaction on any error
                    try:
                        trans.rollback() 
                        logger.warning(f"Transaction rolled back due to error: {inner_e}")
                    except Exception as rollback_e:
                        logger.error(f"Failed to rollback transaction: {rollback_e}")
                    
                    # If it's a transaction error, we need to start fresh
                    if "current transaction is aborted" in str(inner_e).lower() or \
                       "InFailedSqlTransaction" in str(type(inner_e)):
                        logger.warning("Transaction is in failed state, creating new connection")
                        try:
                            connection.close()
                        except:
                            pass
                        # Force a new connection for next retry
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                    
                    # Try without advisory locks as fallback
                    try:
                        logger.info("Retrying without advisory locks...")
                        new_conn = self.engine.connect()
                        new_trans = new_conn.begin()
                        Base.metadata.drop_all(bind=new_conn)
                        new_trans.commit()
                        new_conn.close()
                        logger.warning("Tables dropped successfully without advisory locks")
                        return True
                    except Exception as fallback_e:
                        logger.error(f"Fallback drop also failed: {fallback_e}")
                        raise inner_e
                        
                finally:
                    try:
                        if not connection.closed:
                            connection.close()
                    except:
                        pass
                
            except OperationalError as e:
                error_str = str(e).lower()
                if ("deadlock detected" in error_str or 
                    "current transaction is aborted" in error_str) and attempt < max_retries - 1:
                    logger.warning(f"Database error on attempt {attempt + 1}: {e}")
                    logger.warning(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(f"Failed to drop tables after {attempt + 1} attempts: {e}")
                    return False
                    
            except StatementError as e:
                # Handle SQLAlchemy statement errors (including transaction errors)
                if "current transaction is aborted" in str(e).lower() and attempt < max_retries - 1:
                    logger.warning(f"Transaction aborted on attempt {attempt + 1}, retrying...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"Statement error after {attempt + 1} attempts: {e}")
                    return False
                    
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"Failed to drop tables after {attempt + 1} attempts: {e}")
                    return False
        
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


def get_db():
    """Dependency function to get database session (for FastAPI)."""
    with db_manager.get_session() as session:
        yield session


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