#!/usr/bin/env python3
"""
Main entry point for the BingX Trading Bot API server.
This allows the module to be run with: python -m api
"""

import os
import sys
import uvicorn
import logging
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    """Main entry point for the API server."""
    # Configure logging for startup
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        # Get port from environment (Render uses PORT env var)
        port = int(os.getenv("PORT", 10000))
        host = os.getenv("HOST", "0.0.0.0")
        
        # Log environment info
        logger.info(f"🚀 Starting BingX Trading Bot API server on {host}:{port}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Project root: {project_root}")
        
        # Check critical environment variables
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            logger.info("✅ DATABASE_URL is set")
        else:
            logger.warning("⚠️ DATABASE_URL not set - will use defaults")
        
        # Import the FastAPI app (test for import errors)
        logger.info("📦 Importing FastAPI application...")
        from api.web_api import app
        logger.info("✅ FastAPI application imported successfully")
        
        # Run the server with production-ready settings
        uvicorn.run(
            "api.web_api:app",
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            workers=1,  # Single worker to avoid database conflicts
            timeout_keep_alive=30,
            timeout_graceful_shutdown=10
        )
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.error("This usually means missing dependencies or import issues")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        logger.error("Check environment variables and dependencies")
        sys.exit(1)

if __name__ == "__main__":
    main()