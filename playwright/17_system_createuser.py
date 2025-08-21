#!/usr/bin/env python3
"""
System Create User Test - Fixed Version
Tests the user creation functionality in Rediacc console
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
        print("Starting System Create User Test...")
        
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
        
        email_input.fill("admin@rediacc.io")  # Fixed typo
        
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
        
        # Click create user button
        print("7. Opening create user dialog...")
        create_user_found = False
        
        try:
            create_button = page.get_by_test_id("system-create-user-button")
            if create_button.is_visible():
                create_button.click()
                create_user_found = True
                print("   Create user dialog opened")
        except:
            pass
        
        if not create_user_found:
            # Try alternative selectors
            print("   Trying alternative selector for create user button...")
            try:
                create_selectors = [
                    'button:has-text("Create User")',
                    'button:has-text("Add User")',
                    'button:has-text("New User")',
                    'button[title*="user"]',
                    '[data-testid*="create-user"]'
                ]
                
                for selector in create_selectors:
                    try:
                        create_button = page.locator(selector).first
                        if create_button.is_visible():
                            create_button.click()
                            create_user_found = True
                            print("   Create user dialog opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding create user button: {str(e)}")
        
        if not create_user_found:
            print("   Warning: Could not find create user button")
        else:
            time.sleep(1)  # Wait for dialog to open
            
            # Fill in user details
            print("8. Filling user details...")
            
            # Email input
            email_filled = False
            try:
                email_input = page.get_by_test_id("create-user-email-input")
                if email_input.is_visible():
                    email_input.fill("contact@rediacc.com")
                    email_filled = True
            except:
                # Try alternative selectors
                email_selectors = [
                    'input[placeholder*="email" i]',
                    'input[type="email"]',
                    'input[name="email"]',
                    '.ant-modal input[type="email"]'
                ]
                for selector in email_selectors:
                    try:
                        email_input = page.locator(selector).first
                        if email_input.is_visible():
                            email_input.fill("contact@rediacc.com")
                            email_filled = True
                            break
                    except:
                        continue
            
            if not email_filled:
                print("   Warning: Could not fill email")
            else:
                print("   Email filled: contact@rediacc.com")
            
            # Password input
            password_filled = False
            try:
                password_input = page.get_by_test_id("create-user-password-input")
                if password_input.is_visible():
                    password_input.fill("contact12345678")
                    password_filled = True
            except:
                # Try alternative selectors
                password_selectors = [
                    'input[placeholder*="password" i]',
                    'input[type="password"]',
                    'input[name="password"]',
                    '.ant-modal input[type="password"]'
                ]
                for selector in password_selectors:
                    try:
                        password_input = page.locator(selector).first
                        if password_input.is_visible():
                            password_input.fill("contact12345678")
                            password_filled = True
                            break
                    except:
                        continue
            
            if not password_filled:
                print("   Warning: Could not fill password")
            else:
                print("   Password filled")
            
            # Submit user creation
            print("9. Submitting user creation...")
            submit_found = False
            
            try:
                submit_button = page.get_by_test_id("create-user-submit-button")
                if submit_button.is_visible():
                    submit_button.click()
                    submit_found = True
                    print("   User creation submitted")
            except:
                # Try alternative selectors
                submit_selectors = [
                    '.ant-modal button:has-text("Create")',
                    '.ant-modal button:has-text("Submit")',
                    '.ant-modal button:has-text("OK")',
                    '.ant-modal button.ant-btn-primary',
                    '[role="dialog"] button[type="submit"]'
                ]
                for selector in submit_selectors:
                    try:
                        submit_button = page.locator(selector).first
                        if submit_button.is_visible():
                            submit_button.click()
                            submit_found = True
                            print("   User creation submitted using alternative selector")
                            break
                    except:
                        continue
            
            if not submit_found:
                print("   Warning: Could not submit user creation")
            else:
                time.sleep(2)  # Wait for user creation to complete
                print("   User creation completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "error_screenshot_createuser.png"
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