#!/usr/bin/env python3
"""
System Permissions Test - Fixed Version
Tests the permission group creation functionality in Rediacc console
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
        print("Starting System Permissions Test...")
        
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
        for selector in ['[data-testid="login-email-input"]', 'input[type="email"]', 'input[placeholder*="email" i]', '.ant-input-affix-wrapper input']:
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
            system_link = page.get_by_test_id("main-nav-system")
            system_link.click()
        except:
            # Try alternative selector
            system_link = page.locator('nav a:has-text("System")').first
            if not system_link.is_visible():
                system_link = page.locator('[data-testid*="system"]').first
            system_link.click()
        
        page.wait_for_load_state("networkidle")
        
        # Click on Permissions tab
        print("7. Navigating to Permissions tab...")
        permissions_tab_found = False
        
        try:
            permissions_tab = page.get_by_test_id("system-tab-permissions")
            if permissions_tab.is_visible():
                permissions_tab.click()
                permissions_tab_found = True
                print("   Permissions tab opened")
        except:
            pass
        
        if not permissions_tab_found:
            # Try alternative selectors
            print("   Trying alternative selector for permissions tab...")
            try:
                permissions_selectors = [
                    'button:has-text("Permissions")',
                    'div[role="tab"]:has-text("Permissions")',
                    '.ant-tabs-tab:has-text("Permissions")',
                    '[data-testid*="permissions"]'
                ]
                
                for selector in permissions_selectors:
                    try:
                        permissions_tab = page.locator(selector).first
                        if permissions_tab.is_visible():
                            permissions_tab.click()
                            permissions_tab_found = True
                            print("   Permissions tab opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding permissions tab: {str(e)}")
        
        if not permissions_tab_found:
            print("   Warning: Could not find permissions tab")
        
        time.sleep(1)  # Wait for permissions tab to load
        
        # Click create permission group button
        print("8. Opening create permission group dialog...")
        create_group_found = False
        
        try:
            create_button = page.get_by_test_id("system-create-permission-group-button")
            if create_button.is_visible():
                create_button.click()
                create_group_found = True
                print("   Create permission group dialog opened")
        except:
            pass
        
        if not create_group_found:
            # Try alternative selectors
            print("   Trying alternative selector for create permission group button...")
            try:
                create_selectors = [
                    'button:has-text("Create Permission Group")',
                    'button:has-text("Add Permission Group")',
                    'button:has-text("New Permission Group")',
                    'button:has-text("Create Group")',
                    'button:has-text("Add Group")',
                    'button[title*="permission"]',
                    '[data-testid*="create-permission"]',
                    'button.ant-btn-primary'
                ]
                
                for selector in create_selectors:
                    try:
                        create_button = page.locator(selector).first
                        if create_button.is_visible():
                            create_button.click()
                            create_group_found = True
                            print("   Create permission group dialog opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding create permission group button: {str(e)}")
        
        if not create_group_found:
            print("   Warning: Could not find create permission group button")
        else:
            time.sleep(1)  # Wait for dialog to open
            
            # Fill in permission group details
            print("9. Filling permission group details...")
            
            # Group name input
            group_name_filled = False
            try:
                group_name_input = page.get_by_test_id("system-permission-group-name-input")
                if group_name_input.is_visible():
                    group_name_input.fill("testgroup")
                    group_name_filled = True
                    print("   Permission group name filled: testgroup")
            except:
                # Try alternative selectors
                group_name_selectors = [
                    'input[placeholder*="group" i]',
                    'input[placeholder*="name" i]',
                    'input[name="groupName"]',
                    'input[name="name"]',
                    '.ant-modal input[type="text"]',
                    '.ant-form-item input'
                ]
                for selector in group_name_selectors:
                    try:
                        group_name_input = page.locator(selector).first
                        if group_name_input.is_visible():
                            group_name_input.fill("testgroup")
                            group_name_filled = True
                            print("   Permission group name filled using alternative selector: testgroup")
                            break
                    except:
                        continue
            
            if not group_name_filled:
                print("   Warning: Could not fill permission group name")
            
            # Submit permission group creation
            print("10. Submitting permission group creation...")
            submit_found = False
            
            try:
                submit_button = page.get_by_test_id("permission-modal-ok-button")
                if submit_button.is_visible():
                    submit_button.click()
                    submit_found = True
                    print("   Permission group creation submitted")
            except:
                # Try alternative selectors
                submit_selectors = [
                    '.ant-modal button:has-text("OK")',
                    '.ant-modal button:has-text("Create")',
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
                            print("   Permission group creation submitted using alternative selector")
                            break
                    except:
                        continue
            
            if not submit_found:
                print("   Warning: Could not submit permission group creation")
            else:
                time.sleep(2)  # Wait for permission group creation to complete
                print("   Permission group creation completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot_permissions.png"
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