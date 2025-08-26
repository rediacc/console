#!/usr/bin/env python3
"""
Manual Permission Group Creation Capture
"""

import asyncio
import time
from playwright.sync_api import sync_playwright, expect

def run_test():
    """Run the test to capture permission creation"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        
        try:
            print("1. Navigating to console...")
            page.goto("http://localhost:7322/console")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            
            print("2. Logging in...")
            page.fill('input[type="email"]', 'admin@rediacc.io')
            page.fill('input[type="password"]', 'admin')
            page.click('button[type="submit"]')
            
            # Wait for dashboard
            page.wait_for_url("**/console/dashboard", timeout=10000)
            print("   Login successful!")
            
            print("3. Navigating to System...")
            page.click('text=System')
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            
            print("4. Taking screenshot of System page...")
            page.screenshot(path="01_system_page.png", full_page=True)
            
            print("5. Switching to Expert mode...")
            page.click('label:has-text("Expert")')
            time.sleep(1)
            page.screenshot(path="02_expert_mode.png", full_page=True)
            
            print("6. Clicking Permissions tab...")
            page.click('text=Permissions')
            time.sleep(1)
            page.screenshot(path="03_permissions_tab.png", full_page=True)
            
            print("7. Clicking Create Permission Group button...")
            page.click('button:has-text("Create")')
            time.sleep(1)
            page.screenshot(path="04_create_modal.png", full_page=True)
            
            print("8. Filling group name...")
            page.fill('.ant-modal input[type="text"]', 'TestGroup03')
            time.sleep(1)
            page.screenshot(path="05_group_name_filled.png", full_page=True)
            
            print("9. Submitting...")
            page.click('.ant-modal button:has-text("OK")')
            time.sleep(3)
            page.screenshot(path="06_after_creation.png", full_page=True)
            
            print("Test completed successfully!")
            
        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="error_screenshot.png", full_page=True)
        
        finally:
            time.sleep(2)
            browser.close()

if __name__ == "__main__":
    run_test()