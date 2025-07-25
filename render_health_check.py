#!/usr/bin/env python3
"""
Health check script for Render deployment.
This can be run manually on Render to test if the server is working.
"""

import asyncio
import sys
import os
import time
import traceback
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_server_health():
    """Test if the server can start and respond to health checks."""
    print("🏥 BingX Trading Bot - Render Health Check")
    print("=" * 50)
    
    # Test 1: Environment Variables
    print("\n🧪 Test 1: Environment Variables")
    required_vars = ['DATABASE_URL', 'PORT']
    optional_vars = ['BINGX_API_KEY', 'BINGX_SECRET_KEY']
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: {'*' * min(len(value), 20)}...")
        else:
            print(f"  ❌ {var}: NOT SET (REQUIRED)")
    
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"  ✅ {var}: {'*' * 10}...")
        else:
            print(f"  ⚠️  {var}: NOT SET (optional for health check)")
    
    # Test 2: Critical Imports
    print("\n🧪 Test 2: Critical Imports")
    try:
        print("  🔍 Testing FastAPI...")
        import fastapi
        print(f"    ✅ FastAPI version: {fastapi.__version__}")
        
        print("  🔍 Testing uvicorn...")
        import uvicorn
        print(f"    ✅ Uvicorn version: {uvicorn.__version__}")
        
        print("  🔍 Testing SQLAlchemy...")
        import sqlalchemy
        print(f"    ✅ SQLAlchemy version: {sqlalchemy.__version__}")
        
        print("  🔍 Testing database connection module...")
        from database.connection import get_db, init_database
        print("    ✅ Database module imported successfully")
        
        print("  🔍 Testing API web module...")
        from api.web_api import app
        print("    ✅ FastAPI app imported successfully")
        
        print("  ✅ All critical imports successful!")
        
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        traceback.print_exc()
        return False
    
    # Test 3: FastAPI App Creation
    print("\n🧪 Test 3: FastAPI App Health")
    try:
        from api.web_api import app
        print(f"  ✅ App created: {type(app)}")
        print(f"  ✅ App routes: {len(app.routes)} routes registered")
        
        # Find health route
        health_routes = [route for route in app.routes if hasattr(route, 'path') and route.path == '/health']
        if health_routes:
            print("  ✅ Health check route found")
        else:
            print("  ⚠️  Health check route not found")
        
    except Exception as e:
        print(f"  ❌ FastAPI app test failed: {e}")
        traceback.print_exc()
        return False
    
    # Test 4: Database Connection (if available)
    print("\n🧪 Test 4: Database Connection")
    try:
        from database.connection import init_database, get_session
        
        # Try to initialize database
        init_result = init_database()
        if init_result:
            print("  ✅ Database initialized successfully")
            
            # Try to get a session
            with get_session() as session:
                from sqlalchemy import text
                result = session.execute(text("SELECT 1")).scalar()
                if result == 1:
                    print("  ✅ Database query test passed")
                else:
                    print("  ⚠️  Database query returned unexpected result")
        else:
            print("  ⚠️  Database initialization failed (may be normal if DATABASE_URL not set)")
            
    except Exception as e:
        print(f"  ⚠️  Database test failed: {e} (may be normal if DATABASE_URL not set)")
    
    # Test 5: Server Start Test (Optional)
    print("\n🧪 Test 5: Server Configuration")
    try:
        port = int(os.getenv("PORT", 10000))
        host = os.getenv("HOST", "0.0.0.0")
        print(f"  ✅ Server will bind to: {host}:{port}")
        
        # Test uvicorn configuration
        config = uvicorn.Config(
            "api.web_api:app",
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            workers=1
        )
        print(f"  ✅ Uvicorn config created successfully")
        
    except Exception as e:
        print(f"  ❌ Server configuration failed: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("✅ Health check completed successfully!")
    print("🚀 Server should be able to start now.")
    print("\nIf you're still getting 502 errors:")
    print("1. Check Render build logs for dependency installation issues")
    print("2. Check Render runtime logs for startup errors")
    print("3. Verify all environment variables are set in Render dashboard")
    print("4. Make sure the PORT environment variable is set by Render")
    
    return True

def main():
    """Run the health check."""
    try:
        # Check Python version
        print(f"Python version: {sys.version}")
        print(f"Working directory: {os.getcwd()}")
        print(f"Project root: {project_root}")
        
        # Run async health check
        result = asyncio.run(test_server_health())
        
        if result:
            sys.exit(0)  # Success
        else:
            sys.exit(1)  # Failure
            
    except Exception as e:
        print(f"❌ Health check failed with error: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()