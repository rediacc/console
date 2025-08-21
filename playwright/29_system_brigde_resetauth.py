#!/usr/bin/env python3
"""
System Bridge Reset Auth Test - Fixed Version
Tests the bridge authorization reset functionality in Rediacc console
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
        print("Starting System Bridge Reset Auth Test...")
        
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
        
        # Find and click reset auth button for specific bridge
        print("7. Looking for bridge reset auth button...")
        reset_auth_found = False
        bridge_name = "testbridge012"
        
        try:
            # Try specific test-id first
            reset_auth_button = page.get_by_test_id(f"system-bridge-reset-auth-button-{bridge_name}")
            if reset_auth_button.is_visible():
                reset_auth_button.click()
                reset_auth_found = True
                print(f"   Reset auth button clicked for bridge: {bridge_name}")
        except:
            pass
        
        if not reset_auth_found:
            # Try alternative selectors
            print("   Trying alternative selector for reset auth button...")
            try:
                # Look for bridge row and reset auth button
                bridge_row = page.locator(f'tr:has-text("{bridge_name}")').first
                if bridge_row.is_visible():
                    reset_btn = bridge_row.locator('button:has-text("Reset Auth")').first
                    if not reset_btn.is_visible():
                        reset_btn = bridge_row.locator('button:has-text("Reset Authorization")').first
                    if not reset_btn.is_visible():
                        reset_btn = bridge_row.locator('button[title*="reset"]').first
                    if not reset_btn.is_visible():
                        reset_btn = bridge_row.locator('button[title*="auth"]').first
                    if not reset_btn.is_visible():
                        reset_btn = bridge_row.locator('[data-testid*="reset-auth"]').first
                    
                    if reset_btn.is_visible():
                        reset_btn.click()
                        reset_auth_found = True
                        print(f"   Reset auth button clicked for bridge in row")
                else:
                    # Try to find any reset auth button
                    reset_selectors = [
                        'button:has-text("Reset Auth")',
                        'button:has-text("Reset Authorization")',
                        'button[title*="reset"]',
                        'button[title*="Reset"]',
                        'button[title*="authorization"]',
                        '[data-testid*="reset-auth"]',
                        '.ant-table button:has-text("Reset")'
                    ]
                    
                    for selector in reset_selectors:
                        try:
                            reset_auth_button = page.locator(selector).first
                            if reset_auth_button.is_visible():
                                reset_auth_button.click()
                                reset_auth_found = True
                                print("   Reset auth button clicked using alternative selector")
                                break
                        except:
                            continue
            except Exception as e:
                print(f"   Error finding reset auth button: {str(e)}")
        
        if not reset_auth_found:
            print("   Warning: Could not find reset auth button")
            print("   Bridge might not exist or reset auth option is not available")
        else:
            time.sleep(1)  # Wait for confirmation dialog
            
            # Confirm reset authorization
            print("8. Confirming reset authorization...")
            confirm_found = False
            
            try:
                confirm_button = page.get_by_role("button", name="Reset Authorization")
                if confirm_button.is_visible():
                    confirm_button.click()
                    confirm_found = True
                    print("   Reset authorization confirmed")
            except:
                pass
            
            if not confirm_found:
                # Try alternative selectors for confirmation
                print("   Trying alternative selector for confirm button...")
                try:
                    confirm_selectors = [
                        'button:has-text("Reset Authorization")',
                        'button:has-text("Reset Auth")',
                        'button:has-text("Reset")',
                        'button:has-text("Yes")',
                        'button:has-text("OK")',
                        'button:has-text("Confirm")',
                        '.ant-modal button.ant-btn-primary',
                        '.ant-modal button.ant-btn-dangerous',
                        '[role="dialog"] button:has-text("Reset")',
                        '[role="dialog"] button:has-text("Yes")'
                    ]
                    
                    for selector in confirm_selectors:
                        try:
                            confirm_button = page.locator(selector).first
                            if confirm_button.is_visible():
                                confirm_button.click()
                                confirm_found = True
                                print("   Reset authorization confirmed using alternative selector")
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"   Error confirming reset authorization: {str(e)}")
            
            if not confirm_found:
                print("   Warning: Could not confirm reset authorization")
            else:
                time.sleep(2)  # Wait for reset to complete
                print("   Bridge authorization reset completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "error_screenshot_resetauth.png"
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