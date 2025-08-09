#!/usr/bin/env python3
"""Test script for 07_repo_up_improved.py"""

import subprocess
import sys
from pathlib import Path

def run_test():
    """Run the improved repo up test"""
    print("=" * 60)
    print("Testing 07_repo_up_improved.py")
    print("=" * 60)
    
    # Run the test
    try:
        result = subprocess.run(
            [sys.executable, "07_repo_up_improved.py"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True
        )
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)
        
        print(f"\nReturn code: {result.returncode}")
        
        # Check for expected output
        if "Login successful!" in result.stdout:
            print("✅ Login successful")
        else:
            print("❌ Login might have failed")
            
        if "Resources page loaded successfully" in result.stdout:
            print("✅ Resources page loaded")
        else:
            print("❌ Resources page not loaded")
            
        if "Machine rediacc11 expanded successfully" in result.stdout:
            print("✅ Machine expanded")
        else:
            print("❌ Machine not expanded")
            
        if "Action 'up' triggered" in result.stdout:
            print("✅ Action triggered")
        else:
            print("❌ Action not triggered")
            
        if "Task failed" in result.stdout:
            print("✅ Task failure detected (expected in this test)")
        elif "Task completed successfully" in result.stdout:
            print("✅ Task completed successfully")
        else:
            print("⚠️  Task status unknown")
            
        if "Queue dialog closed" in result.stdout:
            print("✅ Queue dialog closed")
        else:
            print("❌ Queue dialog not closed")
            
    except Exception as e:
        print(f"Error running test: {e}")
        return 1
    
    print("\n" + "=" * 60)
    print("Test complete!")
    return 0

if __name__ == "__main__":
    sys.exit(run_test())