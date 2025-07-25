#!/usr/bin/env python3
"""
Test script to verify if the server starts correctly locally
before debugging Render issues.
"""

import os
import sys
import asyncio
import signal
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_server_startup():
    """Test if the API server can start without errors."""
    print("🧪 Testing local server startup...")
    
    try:
        # Set minimal environment variables for testing
        os.environ.setdefault('PORT', '8000')
        os.environ.setdefault('HOST', '127.0.0.1')
        
        # Import and create the FastAPI app
        from api.web_api import app
        print("✅ FastAPI app imported successfully")
        
        # Import uvicorn
        import uvicorn
        print("✅ Uvicorn imported successfully")
        
        # Test database connection if available
        try:
            from database.connection import init_database, get_session
            print("🗄️ Testing database connection...")
            
            init_result = init_database()
            if init_result:
                print("✅ Database initialized successfully")
                
                # Quick query test
                with get_session() as session:
                    from sqlalchemy import text
                    result = session.execute(text("SELECT 1")).scalar()
                    if result == 1:
                        print("✅ Database query test passed")
            else:
                print("⚠️ Database initialization failed (may be normal without DATABASE_URL)")
                
        except Exception as e:
            print(f"⚠️ Database test failed: {e} (may be normal without DATABASE_URL)")
        
        print("\n🚀 Starting server test...")
        print("Server should start on http://127.0.0.1:8000")
        print("Press Ctrl+C to stop the test")
        print("-" * 50)
        
        # Start the server
        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=8000,
            log_level="info",
            access_log=True
        )
        
        server = uvicorn.Server(config)
        
        # Set up signal handler
        def signal_handler(signum, frame):
            print(f"\n📡 Received signal {signum}, shutting down...")
            server.should_exit = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start server
        await server.serve()
        
    except Exception as e:
        print(f"❌ Server startup failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def main():
    """Main entry point."""
    print("🤖 BingX Trading Bot - Local Server Test")
    print("=" * 50)
    
    try:
        # Run the async test
        asyncio.run(test_server_startup())
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())