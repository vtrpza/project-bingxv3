#!/usr/bin/env python3
"""
Minimal test to verify the exact startup command that Render uses.
This simulates the exact command: python -m api
"""

import sys
import os
from pathlib import Path

def main():
    """Test the exact startup sequence that Render uses."""
    print("🔍 Testing Render startup sequence...")
    print(f"Command: python -m api")
    print(f"Working directory: {os.getcwd()}")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print("-" * 50)
    
    try:
        # This is exactly what happens when Render runs: python -m api
        print("📦 Importing api.__main__...")
        import api.__main__
        print("✅ api.__main__ imported successfully")
        
        print("🚀 Calling api.__main__.main()...")
        # This will actually start the server
        api.__main__.main()
        
    except SystemExit as e:
        print(f"📤 Program exited with code: {e.code}")
        return e.code
    except Exception as e:
        print(f"❌ Error during startup: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())