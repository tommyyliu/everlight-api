#!/usr/bin/env python3
"""
Simple test runner script to run journal endpoint tests
"""
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    import pytest
    
    # Run the journal endpoint tests
    exit_code = pytest.main([
        "tests/test_journal_endpoints.py",
        "-v",
        "-s",
        "--tb=short"
    ])
    
    sys.exit(exit_code)