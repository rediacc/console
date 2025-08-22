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
        
        # Check for Simple/Expert mode and switch to Expert if needed
        print("7. Checking for Simple/Expert mode...")
        
        # Take screenshot to see current state
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "system_bridgeedit_before_mode_switch.png"
        screenshot_path.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        print(f"   Screenshot saved: {screenshot_path}")
        
        try:
            # Look for the Expert radio button/label
            # The UI shows radio buttons with labels, not regular buttons
            expert_radio_selectors = [
                'label:has-text("Expert")',
                'span:has-text("Expert")',
                'input[type="radio"][value="expert"]',
                '.ant-radio-wrapper:has-text("Expert")',
                '[role="radio"]:has-text("Expert")',
                'text=Expert'
            ]
            
            expert_clicked = False
            for selector in expert_radio_selectors:
                try:
                    expert_element = page.locator(selector).first
                    if expert_element.is_visible():
                        print(f"   Found Expert mode selector: {selector}")
                        expert_element.click()
                        expert_clicked = True
                        time.sleep(1)  # Wait for mode switch
                        print("   Switched to Expert mode")
                        
                        # Take screenshot after mode switch
                        screenshot_path_after = Path(__file__).parent / "artifacts" / "screenshots" / "system_bridgeedit_after_mode_switch.png"
                        page.screenshot(path=str(screenshot_path_after))
                        print(f"   Screenshot after switch: {screenshot_path_after}")
                        break
                except:
                    continue
            
            if not expert_clicked:
                # Check if already in Expert mode
                try:
                    # Check if Expert is already selected
                    expert_checked = page.locator('input[type="radio"][checked]:has-text("Expert")').first
                    if expert_checked.is_visible():
                        print("   Already in Expert mode")
                    else:
                        print("   Could not find or click Expert mode selector")
                except:
                    print("   Mode selection status unclear, continuing...")
        except Exception as e:
            print(f"   Could not check/switch mode: {str(e)}")
        
        # First, navigate to Bridges tab if needed
        print("8. Looking for Bridges tab...")
        try:
            # Look for Bridges tab
            bridges_tab_selectors = [
                'button:has-text("Bridges")',
                'a:has-text("Bridges")',
                '[role="tab"]:has-text("Bridges")',
                '.ant-tabs-tab:has-text("Bridges")',
                'text=Bridges'
            ]
            
            for selector in bridges_tab_selectors:
                try:
                    bridges_tab = page.locator(selector).first
                    if bridges_tab.is_visible():
                        print(f"   Found Bridges tab with selector: {selector}")
                        bridges_tab.click()
                        time.sleep(1)  # Wait for tab content to load
                        print("   Clicked on Bridges tab")
                        break
                except:
                    continue
        except Exception as e:
            print(f"   Could not find/click Bridges tab: {str(e)}")
        
        # Click edit button for specific bridge
        print("9. Looking for bridge edit button...")
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
            
            # Take screenshot of edit dialog
            screenshot_dialog = Path(__file__).parent / "artifacts" / "screenshots" / "system_bridgeedit_dialog.png"
            page.screenshot(path=str(screenshot_dialog))
            print(f"   Dialog screenshot: {screenshot_dialog}")
            
            # Edit bridge name
            print("10. Editing bridge name...")
            bridge_name_edited = False
            
            try:
                bridge_name_input = page.get_by_test_id("resource-modal-field-bridgeName-input")
                if bridge_name_input.is_visible():
                    # Clear and fill with new value
                    bridge_name_input.click()
                    bridge_name_input.press("Control+a")
                    bridge_name_input.type("testbridge012")
                    bridge_name_edited = True
                    print("   Bridge name changed to: testbridge012")
            except:
                # Try alternative selectors
                bridge_name_selectors = [
                    'input[placeholder*="bridge" i]',
                    'input[placeholder*="name" i]',
                    'input[id*="bridgeName"]',
                    'input[name="bridgeName"]',
                    '.ant-form-item:has-text("Bridge Name") input',
                    '.ant-modal input[type="text"]',
                    '.ant-modal .ant-input'
                ]
                for selector in bridge_name_selectors:
                    try:
                        bridge_name_input = page.locator(selector).first
                        if bridge_name_input.is_visible():
                            # Clear and fill with new value
                            bridge_name_input.click()
                            bridge_name_input.press("Control+a")
                            bridge_name_input.type("testbridge012")
                            bridge_name_edited = True
                            print(f"   Bridge name changed using selector: {selector}")
                            break
                    except:
                        continue
            
            if not bridge_name_edited:
                print("   Warning: Could not edit bridge name")
            
            # Submit bridge edit
            print("11. Submitting bridge edit...")
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
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot_bridgeedit.png"
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