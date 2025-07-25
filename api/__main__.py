#!/usr/bin/env python3
"""
Main entry point for the BingX Trading Bot API server.
This allows the module to be run with: python -m api
"""

import os
import sys
import uvicorn
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    """Main entry point for the API server."""
    # Get port from environment (Render uses PORT env var)
    port = int(os.getenv("PORT", 10000))
    host = os.getenv("HOST", "0.0.0.0")
    
    # Import the FastAPI app
    from api.web_api import app
    
    print(f"🚀 Starting BingX Trading Bot API server on {host}:{port}")
    
    # Run the server
    uvicorn.run(
        "api.web_api:app",
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main()