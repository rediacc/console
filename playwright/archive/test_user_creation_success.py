#!/usr/bin/env python3
"""
Test User Creation Success Messages
Tests the actual user creation flow to capture success indicators
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

# Load config
config_path = Path("/home/anl/monorepo/console/playwright/config.json")
with open(config_path) as f:
    config = json.load(f)

def test_user_creation_success():
    """Test the complete user creation flow and capture success messages"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(10000)
        
        try:
            print("1. Navigating to console and logging in...")
            page.goto(config['baseUrl'] + "/console")
            
            # Login if needed
            if '/login' in page.url or 'signin' in page.url:
                page.locator('input[type="email"]').fill(config['login']['credentials']['email'])
                page.locator('input[type="password"]').fill(config['login']['credentials']['password'])
                page.locator('button[type="submit"]').click()
                page.wait_for_url("**/console/dashboard")
            
            print("2. Navigating to System page...")
            page.locator('[data-testid="main-nav-system"]').click()
            page.wait_for_load_state("networkidle")
            
            print("3. Opening Create User modal...")
            page.locator('[data-testid="system-create-user-button"]').click()
            
            # Wait for modal to appear
            page.wait_for_selector('.ant-modal', state='visible')
            
            print("4. Filling user creation form...")
            # Generate unique email to avoid conflicts
            import time
            timestamp = str(int(time.time()))
            test_email = f"testuser_{timestamp}@example.com"
            test_password = "TestPass123!"
            
            # Fill form using discovered selectors
            email_input = page.locator('[data-testid="resource-form-field-newUserEmail"]')
            email_input.fill(test_email)
            
            password_input = page.locator('[data-testid="resource-form-field-newUserPassword"]')
            password_input.fill(test_password)
            
            print(f"   Email: {test_email}")
            print(f"   Password: {test_password}")
            
            # Take screenshot before submission
            page.screenshot(path="test_before_submission.png", full_page=True)
            
            print("5. Submitting user creation...")
            submit_button = page.locator('[data-testid="resource-form-submit-button"]')
            submit_button.click()
            
            print("6. Monitoring for success indicators...")
            
            # Wait a moment for processing
            time.sleep(2)
            
            # Look for various success indicators
            success_indicators = [
                '.ant-message-success',
                '.ant-notification-notice-success',
                '[role="alert"]',
                '.toast-success',
                '.notification-success',
                'text="User created successfully"',
                'text="User added successfully"',
                'text="Created successfully"'
            ]
            
            success_found = False
            success_message = ""
            
            for indicator in success_indicators:
                try:
                    element = page.locator(indicator).first
                    if element.is_visible():
                        success_message = element.inner_text()
                        print(f"   SUCCESS INDICATOR FOUND with selector '{indicator}': '{success_message}'")
                        success_found = True
                        break
                except:
                    continue
            
            # Take screenshot after submission
            page.screenshot(path="test_after_submission.png", full_page=True)
            
            # Check if modal closed (indicating success)
            try:
                modal = page.locator('.ant-modal')
                modal_visible = modal.is_visible()
                print(f"   Modal still visible: {modal_visible}")
                if not modal_visible:
                    print("   Modal closed - likely indicates success")
                    success_found = True
            except:
                print("   Modal not found - likely closed")
                success_found = True
            
            # Check if new user appears in the table
            time.sleep(2)  # Give time for refresh
            try:
                new_user_row = page.locator(f'text="{test_email}"').first
                if new_user_row.is_visible():
                    print(f"   NEW USER FOUND in table: {test_email}")
                    success_found = True
                else:
                    print(f"   New user not yet visible in table")
            except:
                print("   Could not check for new user in table")
            
            # Check for any error messages
            error_indicators = [
                '.ant-message-error',
                '.ant-notification-notice-error',
                'text="Error"',
                'text="Failed"',
                '.error-message'
            ]
            
            for error_indicator in error_indicators:
                try:
                    element = page.locator(error_indicator).first
                    if element.is_visible():
                        error_message = element.inner_text()
                        print(f"   ERROR FOUND with selector '{error_indicator}': '{error_message}'")
                except:
                    continue
            
            # Final screenshot
            page.screenshot(path="test_final_state.png", full_page=True)
            
            if success_found:
                print(f"\n✓ USER CREATION APPEARS SUCCESSFUL")
                if success_message:
                    print(f"✓ Success message: '{success_message}'")
            else:
                print(f"\n? USER CREATION STATUS UNCLEAR - check screenshots")
            
            print("\nTest completed! Check screenshots:")
            print("  - test_before_submission.png")
            print("  - test_after_submission.png")
            print("  - test_final_state.png")
            
        except Exception as e:
            print(f"Error during test: {e}")
            page.screenshot(path="test_error.png", full_page=True)
            print("Error screenshot: test_error.png")
            
        finally:
            print("Browser will close in 10 seconds...")
            time.sleep(10)
            browser.close()

if __name__ == "__main__":
    test_user_creation_success()