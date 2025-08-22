#!/usr/bin/env python3
"""
Simple browser test to see current state
"""

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("Navigating to console...")
        page.goto("http://localhost:7322/console")
        time.sleep(3)  # Wait for page load
        
        # Take screenshot of current state
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "current_state.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        print(f"Current URL: {page.url}")
        print(f"Page title: {page.title()}")
        
        # Check if login form is present
        email_inputs = page.locator('input[type="email"]').count()
        password_inputs = page.locator('input[type="password"]').count()
        print(f"Email inputs found: {email_inputs}")
        print(f"Password inputs found: {password_inputs}")
        
        time.sleep(10)  # Keep browser open to inspect
        browser.close()

if __name__ == "__main__":
    run()