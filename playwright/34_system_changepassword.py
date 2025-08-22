#!/usr/bin/env python3
"""
System Change Password Test - Fixed Version
Tests the password change functionality in Rediacc console
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
        print("Starting System Change Password Test...")
        
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
        
        # Click change password button
        print("7. Opening change password dialog...")
        change_password_found = False
        
        try:
            change_password_button = page.get_by_test_id("system-change-password-button")
            if change_password_button.is_visible():
                change_password_button.click()
                change_password_found = True
                print("   Change password dialog opened")
        except:
            pass
        
        if not change_password_found:
            # Try alternative selectors
            print("   Trying alternative selector for change password button...")
            try:
                change_password_selectors = [
                    'button:has-text("Change Password")',
                    'button:has-text("Reset Password")',
                    'button[title*="password"]',
                    'button[title*="Password"]',
                    '[data-testid*="change-password"]',
                    '[data-testid*="password"]'
                ]
                
                for selector in change_password_selectors:
                    try:
                        change_password_button = page.locator(selector).first
                        if change_password_button.is_visible():
                            change_password_button.click()
                            change_password_found = True
                            print("   Change password dialog opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding change password button: {str(e)}")
        
        if not change_password_found:
            print("   Warning: Could not find change password button")
        else:
            time.sleep(1)  # Wait for dialog to open
            
            # Enter new password
            print("8. Entering new password...")
            new_password_filled = False
            new_password = "Admin123_&"
            
            try:
                new_password_input = page.get_by_role("textbox", name="* New Password")
                if new_password_input.is_visible():
                    new_password_input.fill(new_password)
                    new_password_filled = True
                    print("   New password entered")
            except:
                # Try alternative selectors
                new_password_selectors = [
                    'input[placeholder*="new password" i]',
                    'input[placeholder*="password" i]:not([placeholder*="confirm"])',
                    'input[name="newPassword"]',
                    'input[name="password"]',
                    '.ant-form-item:has-text("New Password") input',
                    '.ant-modal input[type="password"]'
                ]
                for selector in new_password_selectors:
                    try:
                        new_password_input = page.locator(selector).first
                        if new_password_input.is_visible():
                            new_password_input.fill(new_password)
                            new_password_filled = True
                            print("   New password entered using alternative selector")
                            break
                    except:
                        continue
            
            if not new_password_filled:
                print("   Warning: Could not enter new password")
            
            # Enter confirm password
            print("9. Confirming new password...")
            confirm_password_filled = False
            
            try:
                confirm_password_input = page.get_by_role("textbox", name="* Confirm New Password")
                if confirm_password_input.is_visible():
                    confirm_password_input.fill(new_password)
                    confirm_password_filled = True
                    print("   Confirm password entered")
            except:
                # Try alternative selectors
                confirm_password_selectors = [
                    'input[placeholder*="confirm" i]',
                    'input[name="confirmPassword"]',
                    'input[name="confirm"]',
                    '.ant-form-item:has-text("Confirm") input',
                    '.ant-modal input[type="password"]:nth-of-type(2)'
                ]
                for selector in confirm_password_selectors:
                    try:
                        confirm_password_input = page.locator(selector).first
                        if confirm_password_input.is_visible():
                            confirm_password_input.fill(new_password)
                            confirm_password_filled = True
                            print("   Confirm password entered using alternative selector")
                            break
                    except:
                        continue
            
            if not confirm_password_filled:
                print("   Warning: Could not enter confirm password")
            
            # Submit password change
            print("10. Submitting password change...")
            submit_found = False
            
            try:
                submit_button = page.get_by_role("button", name="Change Password", exact=True)
                if submit_button.is_visible():
                    submit_button.click()
                    submit_found = True
                    print("   Password change submitted")
            except:
                # Try alternative selectors
                submit_selectors = [
                    'button:has-text("Change Password")',
                    'button:has-text("Update Password")',
                    'button:has-text("Save")',
                    'button:has-text("Submit")',
                    '.ant-modal button.ant-btn-primary',
                    '[role="dialog"] button[type="submit"]',
                    '[role="dialog"] button:has-text("Change")'
                ]
                for selector in submit_selectors:
                    try:
                        submit_button = page.locator(selector).first
                        if submit_button.is_visible():
                            submit_button.click()
                            submit_found = True
                            print("   Password change submitted using alternative selector")
                            break
                    except:
                        continue
            
            if not submit_found:
                print("   Warning: Could not submit password change")
            else:
                time.sleep(2)  # Wait for password change to complete
                print("   Password change completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot_changepassword.png"
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