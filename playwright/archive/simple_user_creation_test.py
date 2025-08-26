#!/usr/bin/env python3
"""
Simple User Creation Test
A focused test to discover success indicators
"""

import json
import time as time_module
from pathlib import Path
from playwright.sync_api import sync_playwright

# Load config
config_path = Path("/home/anl/monorepo/console/playwright/config.json")
with open(config_path) as f:
    config = json.load(f)

def simple_user_creation_test():
    """Simple test to discover success indicators"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(15000)
        
        try:
            print("1. Navigating to dashboard...")
            page.goto(config['baseUrl'] + "/console/dashboard")
            
            # Wait for potential redirect to login
            time_module.sleep(2)
            
            # Check if we need to login
            if '/login' in page.url or 'signin' in page.url:
                print("2. Logging in...")
                email_input = page.locator('input[type="email"], input[placeholder*="email" i]').first
                email_input.fill(config['login']['credentials']['email'])
                
                password_input = page.locator('input[type="password"]').first
                password_input.fill(config['login']['credentials']['password'])
                
                submit_button = page.locator('button[type="submit"], button:has-text("Sign In")').first
                submit_button.click()
                
                page.wait_for_url("**/console/dashboard")
            
            print("3. Navigating to System...")
            page.locator('[data-testid="main-nav-system"]').click()
            page.wait_for_load_state("networkidle")
            
            print("4. Opening Create User modal...")
            create_button = page.locator('[data-testid="system-create-user-button"]')
            create_button.click()
            
            # Wait for modal
            page.wait_for_selector('.ant-modal', state='visible')
            time_module.sleep(1)
            
            print("5. Filling form with test data...")
            timestamp = str(int(time_module.time()))
            test_email = f"test_{timestamp}@example.com"
            test_password = "TestPassword123!"
            
            email_field = page.locator('[data-testid="resource-form-field-newUserEmail"]')
            email_field.fill(test_email)
            
            password_field = page.locator('[data-testid="resource-form-field-newUserPassword"]')
            password_field.fill(test_password)
            
            print(f"   Using email: {test_email}")
            
            # Screenshot before submission
            page.screenshot(path="simple_before_submit.png", full_page=True)
            
            print("6. Submitting form...")
            submit_button = page.locator('[data-testid="resource-form-submit-button"]')
            submit_button.click()
            
            # Wait for response
            time_module.sleep(3)
            
            print("7. Checking for success/error indicators...")
            
            # Check all notification selectors
            notification_selectors = [
                '.ant-message',
                '.ant-notification',
                '[role="alert"]',
                '.notification',
                '.toast',
                '.message'
            ]
            
            for selector in notification_selectors:
                try:
                    elements = page.locator(selector).all()
                    for element in elements:
                        if element.is_visible():
                            text = element.inner_text()
                            classes = element.get_attribute('class')
                            print(f"   NOTIFICATION: '{text}' (classes: {classes})")
                except:
                    continue
            
            # Check if modal is closed
            try:
                modal = page.locator('.ant-modal')
                if not modal.is_visible():
                    print("   SUCCESS: Modal closed automatically")
                else:
                    print("   Modal still visible")
            except:
                print("   Modal check failed")
            
            # Check for new user in table
            time_module.sleep(2)
            try:
                user_row = page.locator(f'text="{test_email}"')
                if user_row.is_visible():
                    print(f"   SUCCESS: New user visible in table: {test_email}")
                else:
                    print("   New user not visible in table yet")
            except:
                print("   Could not check user table")
            
            # Final screenshot
            page.screenshot(path="simple_after_submit.png", full_page=True)
            
            print("\nTest completed! Screenshots:")
            print("- simple_before_submit.png")
            print("- simple_after_submit.png")
            
        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="simple_error.png", full_page=True)
            
        finally:
            print("Keeping browser open for 15 seconds for manual inspection...")
            time_module.sleep(15)
            browser.close()

if __name__ == "__main__":
    simple_user_creation_test()