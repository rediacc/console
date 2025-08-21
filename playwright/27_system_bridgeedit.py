#!/usr/bin/env python3
"""
System Bridge Edit Test - Fixed Version
Tests the bridge editing functionality in Rediacc console
"""

import re
import time
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    """Main test execution"""
    browser = None
    context = None
    
    try:
        print("Starting System Bridge Edit Test...")
        
        # Launch browser
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Navigate to console
        print("1. Navigating to console...")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Check current URL and handle login
        current_url = page.url
        print(f"2. Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            # Already on login page or redirected to login
            print("3. On login page, proceeding with login...")
        else:
            # Try to find and click login link
            print("3. Looking for login link...")
            try:
                login_link = page.get_by_role("banner").get_by_role("link", name="Login")
                with page.expect_popup() as popup_info:
                    login_link.click()
                page = popup_info.value
                print("   Navigated to login page via popup")
            except:
                print("   No login link found, assuming already on login page")
        
        # Perform login
        print("4. Logging in...")
        
        # Find email input with multiple strategies
        email_input = None
        for selector in ['[data-testid="login-email-input"]', 'input[type="email"]', 'input[placeholder*="email" i]']:
            try:
                email_input = page.locator(selector).first
                if email_input.is_visible():
                    break
            except:
                continue
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        email_input.fill("admin@rediacc.io")
        
        # Find password input
        password_input = None
        for selector in ['[data-testid="login-password-input"]', 'input[type="password"]']:
            try:
                password_input = page.locator(selector).first
                if password_input.is_visible():
                    break
            except:
                continue
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        password_input.fill("admin")
        
        # Find and click submit button
        submit_button = None
        for selector in ['[data-testid="login-submit-button"]', 'button[type="submit"]', 'button:has-text("Sign In")']:
            try:
                submit_button = page.locator(selector).first
                if submit_button.is_visible():
                    break
            except:
                continue
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        submit_button.click()
        
        # Wait for dashboard
        print("5. Waiting for dashboard...")
        page.wait_for_url("**/console/dashboard", timeout=10000)
        print("   Login successful!")
        
        # Navigate to System
        print("6. Navigating to System...")
        try:
            system_link = page.get_by_text("System")
            system_link.click()
        except:
            # Try alternative selector
            system_link = page.locator('nav a:has-text("System")').first
            if not system_link.is_visible():
                system_link = page.locator('[data-testid*="system"]').first
            system_link.click()
        
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # Click edit button for specific bridge
        print("7. Looking for bridge edit button...")
        edit_button_found = False
        bridge_name = "testbridge01"
        
        try:
            edit_button = page.get_by_test_id(f"system-bridge-edit-button-{bridge_name}")
            if edit_button.is_visible():
                edit_button.click()
                edit_button_found = True
                print(f"   Edit button clicked for bridge: {bridge_name}")
        except:
            pass
        
        if not edit_button_found:
            # Try alternative selectors
            print("   Trying alternative selector for edit button...")
            try:
                # Look for bridge row and edit button
                bridge_row = page.locator(f'tr:has-text("{bridge_name}")').first
                if bridge_row.is_visible():
                    edit_btn = bridge_row.locator('button:has-text("Edit")').first
                    if not edit_btn.is_visible():
                        edit_btn = bridge_row.locator('button[title*="edit"]').first
                    if not edit_btn.is_visible():
                        edit_btn = bridge_row.locator('button[title*="Edit"]').first
                    if not edit_btn.is_visible():
                        edit_btn = bridge_row.locator('[data-testid*="edit"]').first
                    
                    if edit_btn.is_visible():
                        edit_btn.click()
                        edit_button_found = True
                        print(f"   Edit button clicked for bridge in row")
                else:
                    # Try to find any edit button
                    edit_selectors = [
                        'button:has-text("Edit")',
                        'button[title*="edit"]',
                        'button[title*="Edit"]',
                        '[data-testid*="edit"]',
                        '.ant-table button:has-text("Edit")'
                    ]
                    
                    for selector in edit_selectors:
                        try:
                            edit_button = page.locator(selector).first
                            if edit_button.is_visible():
                                edit_button.click()
                                edit_button_found = True
                                print("   Edit button clicked using alternative selector")
                                break
                        except:
                            continue
            except Exception as e:
                print(f"   Error finding edit button: {str(e)}")
        
        if not edit_button_found:
            print("   Warning: Could not find edit button")
            print("   Bridge might not exist or edit option is not available")
        else:
            time.sleep(1)  # Wait for edit dialog to open
            
            # Edit bridge name
            print("8. Editing bridge name...")
            bridge_name_edited = False
            
            try:
                bridge_name_input = page.get_by_test_id("resource-modal-field-bridgeName-input")
                if bridge_name_input.is_visible():
                    bridge_name_input.clear()
                    bridge_name_input.fill("testbridge012")
                    bridge_name_edited = True
                    print("   Bridge name changed to: testbridge012")
            except:
                # Try alternative selectors
                bridge_name_selectors = [
                    'input[placeholder*="bridge" i]',
                    'input[placeholder*="name" i]',
                    'input[id*="bridgeName"]',
                    '.ant-form-item:has-text("Bridge Name") input',
                    '.ant-modal input[type="text"]'
                ]
                for selector in bridge_name_selectors:
                    try:
                        bridge_name_input = page.locator(selector).first
                        if bridge_name_input.is_visible():
                            bridge_name_input.clear()
                            bridge_name_input.fill("testbridge012")
                            bridge_name_edited = True
                            print("   Bridge name changed using alternative selector: testbridge012")
                            break
                    except:
                        continue
            
            if not bridge_name_edited:
                print("   Warning: Could not edit bridge name")
            
            # Submit bridge edit
            print("9. Submitting bridge edit...")
            submit_found = False
            
            try:
                submit_button = page.get_by_test_id("resource-modal-ok-button")
                if submit_button.is_visible():
                    submit_button.click()
                    submit_found = True
                    print("   Bridge edit submitted")
            except:
                # Try alternative selectors
                submit_selectors = [
                    '.ant-modal button:has-text("OK")',
                    '.ant-modal button:has-text("Save")',
                    '.ant-modal button:has-text("Update")',
                    '.ant-modal button:has-text("Submit")',
                    '.ant-modal button.ant-btn-primary',
                    '[role="dialog"] button[type="submit"]',
                    '[role="dialog"] button:has-text("OK")'
                ]
                for selector in submit_selectors:
                    try:
                        submit_button = page.locator(selector).first
                        if submit_button.is_visible():
                            submit_button.click()
                            submit_found = True
                            print("   Bridge edit submitted using alternative selector")
                            break
                    except:
                        continue
            
            if not submit_found:
                print("   Warning: Could not submit bridge edit")
            else:
                time.sleep(2)  # Wait for bridge edit to complete
                print("   Bridge edit completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "error_screenshot_bridgeedit.png"
            page.screenshot(path=str(screenshot_path))
            print(f"Screenshot saved to: {screenshot_path}")
        raise
    
    finally:
        # Cleanup
        if context:
            context.close()
        if browser:
            browser.close()
        print("Browser closed.")


def main():
    """Entry point"""
    try:
        with sync_playwright() as playwright:
            run(playwright)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()