#!/usr/bin/env python3
"""Quick test to check navigation"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

config_path = Path("/home/anl/monorepo/console/playwright/config.json")
with open(config_path) as f:
    config = json.load(f)

def quick_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(15000)
        
        try:
            print("1. Going to console...")
            page.goto(config['baseUrl'] + "/console")
            
            # Check URL after navigation
            print(f"Current URL: {page.url}")
            
            # Look for login form
            if page.locator('input[type="email"]').is_visible():
                print("2. Login form found, logging in...")
                page.locator('input[type="email"]').fill(config['login']['credentials']['email'])
                page.locator('input[type="password"]').fill(config['login']['credentials']['password'])
                page.locator('button[type="submit"]').click()
                page.wait_for_url("**/console/dashboard")
                print("   Login successful")
            
            # Take screenshot
            page.screenshot(path="quick_after_login.png", full_page=True)
            
            # Look for System navigation
            print("3. Looking for System navigation...")
            system_nav = page.locator('[data-testid="main-nav-system"]')
            if system_nav.is_visible():
                print("   Found System nav")
                system_nav.click()
                page.wait_for_load_state("networkidle")
                page.screenshot(path="quick_system_page.png", full_page=True)
            else:
                print("   System nav not found")
                # Look for any navigation
                nav_items = page.locator('nav a, [data-testid*="nav"]').all()
                print(f"   Found {len(nav_items)} nav items")
                for i, item in enumerate(nav_items[:10]):
                    try:
                        text = item.inner_text()
                        testid = item.get_attribute('data-testid')
                        print(f"     {i}: {text} (testid: {testid})")
                    except:
                        pass
            
        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="quick_error.png")
        finally:
            input("Press Enter to close browser...")
            browser.close()

if __name__ == "__main__":
    quick_test()