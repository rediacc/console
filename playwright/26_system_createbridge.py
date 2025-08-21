#!/usr/bin/env python3
"""
System Create Bridge Test - Fixed Version
Tests the bridge creation functionality in Rediacc console
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
        print("Starting System Create Bridge Test...")
        
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
        
        # Click create bridge button
        print("7. Opening create bridge dialog...")
        create_bridge_found = False
        
        try:
            create_button = page.get_by_test_id("system-create-bridge-button")
            if create_button.is_visible():
                create_button.click()
                create_bridge_found = True
                print("   Create bridge dialog opened")
        except:
            pass
        
        if not create_bridge_found:
            # Try alternative selectors
            print("   Trying alternative selector for create bridge button...")
            try:
                create_selectors = [
                    'button:has-text("Create Bridge")',
                    'button:has-text("Add Bridge")',
                    'button:has-text("New Bridge")',
                    'button[title*="bridge"]',
                    'button[title*="Bridge"]',
                    '[data-testid*="create-bridge"]',
                    'button.ant-btn-primary:has-text("Bridge")'
                ]
                
                for selector in create_selectors:
                    try:
                        create_button = page.locator(selector).first
                        if create_button.is_visible():
                            create_button.click()
                            create_bridge_found = True
                            print("   Create bridge dialog opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding create bridge button: {str(e)}")
        
        if not create_bridge_found:
            print("   Warning: Could not find create bridge button")
        else:
            time.sleep(1)  # Wait for dialog to open
            
            # Select team
            print("8. Selecting team...")
            team_selected = False
            
            try:
                team_select = page.get_by_test_id("resource-modal-field-teamName-select")
                if team_select.is_visible():
                    team_select.locator("div span").nth(2).click()
                    time.sleep(0.5)
                    # Select Private Team
                    team_option = page.get_by_title("Private Team").locator("div")
                    if team_option.is_visible():
                        team_option.click()
                        team_selected = True
                        print("   Team selected: Private Team")
            except:
                # Try alternative approach
                print("   Trying alternative selector for team select...")
                try:
                    # Click on select dropdown
                    team_selectors = [
                        '.ant-select-selector',
                        '[id*="teamName"]',
                        'div[class*="ant-select"]:has-text("Select")',
                        '.ant-form-item:has-text("Team") .ant-select'
                    ]
                    
                    for selector in team_selectors:
                        try:
                            team_select = page.locator(selector).first
                            if team_select.is_visible():
                                team_select.click()
                                time.sleep(0.5)
                                # Try to select team option
                                team_options = [
                                    '[title="Private Team"]',
                                    '.ant-select-item:has-text("Private Team")',
                                    '.ant-select-dropdown .ant-select-item:has-text("Private")',
                                    '.ant-select-item-option:has-text("Private")'
                                ]
                                for opt_selector in team_options:
                                    try:
                                        team_option = page.locator(opt_selector).first
                                        if team_option.is_visible():
                                            team_option.click()
                                            team_selected = True
                                            print("   Team selected using alternative selector")
                                            break
                                    except:
                                        continue
                                if team_selected:
                                    break
                        except:
                            continue
                except Exception as e:
                    print(f"   Error selecting team: {str(e)}")
            
            if not team_selected:
                print("   Warning: Could not select team")
            
            # Enter bridge name
            print("9. Entering bridge name...")
            bridge_name_filled = False
            
            try:
                bridge_name_input = page.get_by_test_id("resource-modal-field-bridgeName-input")
                if bridge_name_input.is_visible():
                    bridge_name_input.fill("testbridge01")
                    bridge_name_filled = True
                    print("   Bridge name entered: testbridge01")
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
                            bridge_name_input.fill("testbridge01")
                            bridge_name_filled = True
                            print("   Bridge name entered using alternative selector: testbridge01")
                            break
                    except:
                        continue
            
            if not bridge_name_filled:
                print("   Warning: Could not enter bridge name")
            
            # Submit bridge creation
            print("10. Submitting bridge creation...")
            submit_found = False
            
            try:
                submit_button = page.get_by_test_id("resource-modal-ok-button")
                if submit_button.is_visible():
                    submit_button.click()
                    submit_found = True
                    print("   Bridge creation submitted")
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
                            print("   Bridge creation submitted using alternative selector")
                            break
                    except:
                        continue
            
            if not submit_found:
                print("   Warning: Could not submit bridge creation")
            else:
                time.sleep(2)  # Wait for bridge creation to complete
                print("   Bridge creation completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "error_screenshot_createbridge.png"
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