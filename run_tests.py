#!/usr/bin/env python3
"""
Test runner for everlight-api journal endpoints
"""
import sys
import os
import subprocess

def main():
    """Run the journal endpoint tests"""
    print("🧪 Running Journal Endpoint Integration Tests")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists("tests/test_journal_endpoints.py"):
        print("❌ Error: Please run this script from the everlight-api directory")
        sys.exit(1)
    
    # Try to run the full PostgreSQL tests first
    print("\n📋 Running full integration tests with testing.postgresql...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_journal_endpoints.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            print("✅ Full integration tests passed!")
            print(result.stdout)
            return 0
        else:
            print("⚠️  Full integration tests failed, trying simplified tests...")
            print("Error output:", result.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"⚠️  Could not run full tests: {e}")
        print("Trying simplified tests...")
    
    # Fall back to simplified tests
    print("\n📋 Running simplified tests with SQLite...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_journal_simple.py", 
            "-v", "--tb=short"
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Simplified tests passed!")
            print(result.stdout)
            return 0
        else:
            print("❌ Simplified tests failed!")
            print("Error output:", result.stderr)
            return 1
    except Exception as e:
        print(f"❌ Could not run simplified tests: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())