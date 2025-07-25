#!/usr/bin/env python3
"""
Test script to verify that FastAPI deprecation warnings are fixed.
"""

import warnings
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_no_deprecation_warnings():
    """Test that importing the FastAPI app doesn't generate deprecation warnings."""
    print("🧪 Testing for FastAPI deprecation warnings...")
    
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        try:
            # Import the FastAPI app
            from api.web_api import app
            print("✅ FastAPI app imported successfully")
            
            # Check for deprecation warnings
            deprecation_warnings = [warning for warning in w if issubclass(warning.category, DeprecationWarning)]
            
            if deprecation_warnings:
                print(f"❌ Found {len(deprecation_warnings)} deprecation warning(s):")
                for warning in deprecation_warnings:
                    print(f"  - {warning.category.__name__}: {warning.message}")
                    print(f"    File: {warning.filename}:{warning.lineno}")
                return False
            else:
                print("✅ No deprecation warnings found!")
                return True
                
        except Exception as e:
            print(f"❌ Error importing FastAPI app: {e}")
            return False

def main():
    """Main test function."""
    print("🤖 BingX Trading Bot - Deprecation Warning Test")
    print("=" * 50)
    
    success = test_no_deprecation_warnings()
    
    if success:
        print("\n✅ All tests passed! No deprecation warnings detected.")
        return 0
    else:
        print("\n❌ Test failed! Deprecation warnings still present.")
        return 1

if __name__ == "__main__":
    sys.exit(main())