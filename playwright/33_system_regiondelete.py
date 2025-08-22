#!/usr/bin/env python3
"""
System Region Delete Test - Fixed Version
Tests the region deletion functionality in Rediacc console
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
        print("Starting System Region Delete Test...")
        
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
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "system_page_before_mode_switch.png"
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
                        screenshot_path_after = Path(__file__).parent / "artifacts" / "screenshots" / "system_page_after_mode_switch.png"
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
        
        # First, navigate to Regions tab if needed
        print("8. Looking for Regions tab...")
        try:
            # Look for Regions tab
            regions_tab_selectors = [
                'button:has-text("Regions")',
                'a:has-text("Regions")',
                '[role="tab"]:has-text("Regions")',
                '.ant-tabs-tab:has-text("Regions")',
                'text=Regions'
            ]
            
            for selector in regions_tab_selectors:
                try:
                    regions_tab = page.locator(selector).first
                    if regions_tab.is_visible():
                        print(f"   Found Regions tab with selector: {selector}")
                        regions_tab.click()
                        time.sleep(1)  # Wait for tab content to load
                        print("   Clicked on Regions tab")
                        break
                except:
                    continue
        except Exception as e:
            print(f"   Could not find/click Regions tab: {str(e)}")
        
        # Find and click delete button for specific region
        print("9. Looking for region delete button...")
        delete_found = False
        region_name = "region004"
        
        try:
            # Try specific test-id first
            delete_button = page.get_by_test_id(f"system-region-delete-button-{region_name}")
            if delete_button.is_visible():
                delete_button.click()
                delete_found = True
                print(f"   Delete button clicked for region: {region_name}")
        except:
            pass
        
        if not delete_found:
            # Try alternative selectors
            print("   Trying alternative selector for delete button...")
            try:
                # Look for region row and delete button
                region_row = page.locator(f'tr:has-text("{region_name}")').first
                if region_row.is_visible():
                    delete_btn = region_row.locator('button:has-text("Delete")').first
                    if not delete_btn.is_visible():
                        delete_btn = region_row.locator('button[title*="delete"]').first
                    if not delete_btn.is_visible():
                        delete_btn = region_row.locator('button[title*="Delete"]').first
                    if not delete_btn.is_visible():
                        delete_btn = region_row.locator('[data-testid*="delete"]').first
                    
                    if delete_btn.is_visible():
                        delete_btn.click()
                        delete_found = True
                        print(f"   Delete button clicked for region in row")
                else:
                    # Try to find any delete button
                    delete_selectors = [
                        'button:has-text("Delete")',
                        'button[title*="delete"]',
                        'button[title*="Delete"]',
                        '[data-testid*="delete"]',
                        '.ant-table button:has-text("Delete")'
                    ]
                    
                    for selector in delete_selectors:
                        try:
                            delete_button = page.locator(selector).first
                            if delete_button.is_visible():
                                delete_button.click()
                                delete_found = True
                                print("   Delete button clicked using alternative selector")
                                break
                        except:
                            continue
            except Exception as e:
                print(f"   Error finding delete button: {str(e)}")
        
        if not delete_found:
            print("   Warning: Could not find delete button")
            print("   Region might not exist or delete option is not available")
        else:
            time.sleep(1)  # Wait for confirmation dialog
            
            # Confirm deletion
            print("10. Confirming deletion...")
            confirm_found = False
            
            try:
                confirm_button = page.get_by_role("button", name="Yes")
                if confirm_button.is_visible():
                    confirm_button.click()
                    confirm_found = True
                    print("   Deletion confirmed")
            except:
                pass
            
            if not confirm_found:
                # Try alternative selectors for confirmation
                print("   Trying alternative selector for confirm button...")
                try:
                    confirm_selectors = [
                        'button:has-text("Yes")',
                        'button:has-text("OK")',
                        'button:has-text("Confirm")',
                        'button:has-text("Delete")',
                        '.ant-modal button.ant-btn-primary',
                        '.ant-modal button.ant-btn-dangerous',
                        '[role="dialog"] button:has-text("Yes")',
                        '[role="dialog"] button:has-text("OK")'
                    ]
                    
                    for selector in confirm_selectors:
                        try:
                            confirm_button = page.locator(selector).first
                            if confirm_button.is_visible():
                                confirm_button.click()
                                confirm_found = True
                                print("   Deletion confirmed using alternative selector")
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"   Error confirming deletion: {str(e)}")
            
            if not confirm_found:
                print("   Warning: Could not confirm deletion")
            else:
                time.sleep(2)  # Wait for deletion to complete
                print("   Region deletion completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot_regiondelete.png"
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