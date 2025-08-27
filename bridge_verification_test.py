#!/usr/bin/env python3
"""
Quick Bridge Verification Test
Just navigates to System > Bridges tab and takes a screenshot to verify bridge creation
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


def run_verification(playwright: Playwright):
    """Quick verification of bridges list"""
    try:
        print("Starting Bridge Verification Test...")
        
        # Load config
        config_path = Path("/home/anl/monorepo/console/playwright/config.json")
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Launch browser
        browser = playwright.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(10000)
        
        # Login
        print("Logging in...")
        page.goto(f"{config['baseUrl']}/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Fill login form
        page.fill('[data-testid="login-email-input"]', config['login']['credentials']['email'])
        page.fill('[data-testid="login-password-input"]', config['login']['credentials']['password'])
        page.click('[data-testid="login-submit-button"]')
        
        # Wait for dashboard
        page.wait_for_url("**/console/dashboard", timeout=10000)
        print("Login successful!")
        
        # Navigate to System
        print("Navigating to System...")
        page.click('[data-testid="main-nav-system"]')
        page.wait_for_load_state("networkidle", timeout=5000)
        
        # Switch to Expert mode
        print("Switching to Expert mode...")
        expert_mode = page.locator('label:has-text("Expert")').first
        if expert_mode.is_visible():
            expert_mode.click()
            page.wait_for_timeout(1000)
        
        # Navigate to Bridges tab
        print("Navigating to Bridges tab...")
        bridges_tab = page.locator('[role="tab"]:has-text("Bridges")').first
        if bridges_tab.is_visible():
            bridges_tab.click()
            page.wait_for_load_state("networkidle", timeout=3000)
            print("Bridges tab opened successfully")
        else:
            print("Bridges tab not found")
        
        # Take screenshot
        screenshot_path = "/home/anl/monorepo/console/bridge_verification_final.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Look for our test bridge
        bridge_name = "test_bridge_smart_verify"
        bridge_row = page.locator(f'tr:has-text("{bridge_name}")').first
        if bridge_row.is_visible():
            print(f"✅ SUCCESS: Bridge '{bridge_name}' found in bridges list!")
        else:
            print(f"⚠️  Bridge '{bridge_name}' not visible in current view")
            
        # Count total bridges
        bridge_rows = page.locator('table tbody tr').count()
        print(f"Total bridges visible: {bridge_rows}")
        
        # Keep browser open for a moment
        page.wait_for_timeout(3000)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        if 'page' in locals():
            page.screenshot(path="/home/anl/monorepo/console/bridge_verification_error.png")
    finally:
        if 'context' in locals():
            context.close()
        if 'browser' in locals():
            browser.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run_verification(playwright)