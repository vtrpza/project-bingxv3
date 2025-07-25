#!/usr/bin/env python3
"""
Quick startup test to diagnose issues before full server startup.
Run this to test if all imports and basic functionality work.
"""

import sys
import os
import traceback
from pathlib import Path

def test_imports():
    """Test all critical imports."""
    print("🧪 Testing imports...")
    
    try:
        print("  ✓ Testing FastAPI...")
        import fastapi
        
        print("  ✓ Testing uvicorn...")
        import uvicorn
        
        print("  ✓ Testing SQLAlchemy...")
        import sqlalchemy
        
        print("  ✓ Testing psycopg2...")
        import psycopg2
        
        print("  ✓ Testing database connection module...")
        from database.connection import get_db, init_database
        
        print("  ✓ Testing API web module...")
        from api.web_api import app
        
        print("✅ All imports successful!")
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        traceback.print_exc()
        return False

def test_environment():
    """Test environment variables."""
    print("\n🧪 Testing environment...")
    
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        print(f"  ✓ DATABASE_URL: {db_url[:50]}...")
    else:
        print("  ⚠️  DATABASE_URL not set")
    
    port = os.getenv("PORT", "10000")
    print(f"  ✓ PORT: {port}")
    
    bingx_key = os.getenv("BINGX_API_KEY")
    if bingx_key:
        print(f"  ✓ BINGX_API_KEY: {bingx_key[:10]}...")
    else:
        print("  ⚠️  BINGX_API_KEY not set")
    
    return True

def test_database():
    """Test database connection."""
    print("\n🧪 Testing database connection...")
    
    try:
        from database.connection import init_database
        result = init_database()
        if result:
            print("  ✅ Database connection successful!")
        else:
            print("  ⚠️  Database connection failed (but app can still start)")
        return True
    except Exception as e:
        print(f"  ❌ Database test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 BingX Trading Bot - Startup Diagnostic Test")
    print("=" * 50)
    
    # Test imports
    if not test_imports():
        print("❌ Critical import failure - server will not start")
        sys.exit(1)
    
    # Test environment
    test_environment()
    
    # Test database
    test_database()
    
    print("\n" + "=" * 50)
    print("✅ Startup test completed - server should be able to start")
    print("If the server still fails, check Render logs for runtime errors")

if __name__ == "__main__":
    main()