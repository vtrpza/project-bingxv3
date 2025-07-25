#!/usr/bin/env python3
"""
Debug script for Render deployment issues.
Run this on Render to get detailed information about the environment.
"""

import os
import sys
import time
import subprocess
import traceback
from pathlib import Path

def run_command(cmd):
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return f"Exit code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Command failed: {e}"

def main():
    """Run comprehensive diagnostics."""
    print("🔍 BingX Trading Bot - Render Debug Information")
    print("=" * 60)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print()
    
    # System Information
    print("📱 System Information")
    print("-" * 30)
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print(f"Platform: {sys.platform}")
    print(f"Working directory: {os.getcwd()}")
    print(f"Script location: {Path(__file__).parent}")
    print()
    
    # Environment Variables
    print("🌍 Environment Variables")
    print("-" * 30)
    important_vars = [
        'PORT', 'HOST', 'DATABASE_URL', 'REDIS_URL',
        'BINGX_API_KEY', 'BINGX_SECRET_KEY', 'SECRET_KEY',
        'PYTHON_VERSION', 'RENDER', 'RENDER_SERVICE_NAME'
    ]
    
    for var in important_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive data
            if 'key' in var.lower() or 'secret' in var.lower() or 'url' in var.lower():
                masked = value[:10] + '*' * (len(value) - 10) if len(value) > 10 else '*' * len(value)
                print(f"  {var}: {masked}")
            else:
                print(f"  {var}: {value}")
        else:
            print(f"  {var}: NOT SET")
    print()
    
    # File System
    print("📁 File System")
    print("-" * 30)
    project_files = [
        'requirements.txt', 'render.yaml', 'main.py',
        'api/__init__.py', 'api/__main__.py', 'api/web_api.py',
        'database/__init__.py', 'database/connection.py',
        'config/__init__.py', 'config/settings.py'
    ]
    
    for file_path in project_files:
        full_path = Path(file_path)
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"  ✅ {file_path} ({size} bytes)")
        else:
            print(f"  ❌ {file_path} (missing)")
    print()
    
    # Python Path
    print("🐍 Python Path")
    print("-" * 30)
    for i, path in enumerate(sys.path):
        print(f"  [{i}] {path}")
    print()
    
    # Installed Packages
    print("📦 Installed Packages (key dependencies)")
    print("-" * 30)
    key_packages = [
        'fastapi', 'uvicorn', 'sqlalchemy', 'psycopg2', 'psycopg2-binary',
        'ccxt', 'pandas', 'numpy', 'asyncio'
    ]
    
    for package in key_packages:
        try:
            __import__(package)
            module = sys.modules[package]
            version = getattr(module, '__version__', 'unknown')
            print(f"  ✅ {package}: {version}")
        except ImportError:
            print(f"  ❌ {package}: NOT INSTALLED")
    print()
    
    # Network and Ports
    print("🌐 Network Information")
    print("-" * 30)
    print("Checking port availability...")
    port = os.getenv('PORT', '10000')
    
    # Check if port is already in use
    netstat_output = run_command(f"netstat -tuln | grep :{port}")
    if f":{port}" in netstat_output:
        print(f"  ⚠️  Port {port} may be in use:")
        print(f"  {netstat_output}")
    else:
        print(f"  ✅ Port {port} appears to be available")
    print()
    
    # Process Information
    print("⚙️  Process Information")
    print("-" * 30)
    process_info = run_command("ps aux | head -20")
    print(process_info)
    print()
    
    # Memory Information
    print("💾 Memory Information")
    print("-" * 30)
    memory_info = run_command("free -h")
    print(memory_info)
    print()
    
    # Import Test
    print("🧪 Critical Import Test")
    print("-" * 30)
    try:
        print("Testing imports...")
        
        print("  🔍 FastAPI...")
        import fastapi
        print(f"    ✅ FastAPI {fastapi.__version__}")
        
        print("  🔍 Uvicorn...")
        import uvicorn
        print(f"    ✅ Uvicorn {uvicorn.__version__}")
        
        print("  🔍 Database connection...")
        from database.connection import get_db, init_database
        print("    ✅ Database module imported")
        
        print("  🔍 API web module...")
        from api.web_api import app
        print("    ✅ FastAPI app imported")
        
        print("  ✅ All critical imports successful!")
        
    except Exception as e:
        print(f"  ❌ Import test failed: {e}")
        traceback.print_exc()
    print()
    
    # Final Recommendations
    print("💡 Troubleshooting Recommendations")
    print("-" * 30)
    print("If you're still experiencing 502 errors, check:")
    print("1. Build logs in Render dashboard for dependency issues")
    print("2. Runtime logs in Render dashboard for startup errors")
    print("3. Ensure all environment variables are set correctly")
    print("4. Verify that the startCommand in render.yaml is correct")
    print("5. Check if there are any firewall or security group issues")
    print()
    
    print("🔧 To manually test the server:")
    print("1. Run: python render_health_check.py")
    print("2. Run: python -m api")
    print("3. Check health endpoint: curl http://localhost:$PORT/health")
    print()
    
    print("=" * 60)
    print("✅ Debug information collection completed!")

if __name__ == "__main__":
    main()