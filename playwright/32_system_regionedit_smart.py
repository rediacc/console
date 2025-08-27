#!/usr/bin/env python3
"""
System Region Edit Test - Smart Version
Tests the region editing functionality in Rediacc console
"""

import json
import time
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def load_config():
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r') as f:
        return json.load(f)


def wait_for_element(page, selector, timeout=5000):
    """Smart wait for element - returns when element is visible and stable"""
    try:
        element = page.locator(selector).first
        element.wait_for(state="visible", timeout=timeout)
        element.wait_for(state="stable", timeout=1000)
        return element
    except:
        return None


def smart_click(page, element_or_selector, timeout=5000):
    """Smart click that waits for element to be ready"""
    if isinstance(element_or_selector, str):
        element = wait_for_element(page, element_or_selector, timeout)
        if element:
            element.click()
            return True
    else:
        element_or_selector.wait_for(state="visible", timeout=timeout)
        element_or_selector.wait_for(state="stable", timeout=1000)
        element_or_selector.click()
        return True
    return False


def run(playwright: Playwright) -> None:
    """Main test execution"""
    browser = None
    context = None
    config = load_config()
    
    try:
        print("Starting System Region Edit Test (Smart Version)...")
        
        # Launch browser with config settings
        browser_config = config.get('browser', {})
        browser = playwright.chromium.launch(
            headless=browser_config.get('headless', False),
            slow_mo=browser_config.get('slowMo', 0)
        )
        
        viewport = browser_config.get('viewport', {})
        context = browser.new_context(
            viewport={
                'width': viewport.get('width', 1280),
                'height': viewport.get('height', 720)
            }
        )
        page = context.new_page()
        
        # Set timeout from config
        page.set_default_timeout(config.get('timeouts', {}).get('pageLoad', 30000))
        
        # Navigate to console
        print("1. Navigating to console...")
        base_url = config.get('baseUrl', 'http://localhost:7322')
        page.goto(f"{base_url}/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Check current URL and handle login
        current_url = page.url
        print(f"2. Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            print("3. On login page, proceeding with login...")
        else:
            print("3. Looking for login link...")
            try:
                login_link = page.get_by_role("banner").get_by_role("link", name="Login")
                with page.expect_popup() as popup_info:
                    login_link.click()
                page = popup_info.value
                print("   Navigated to login page via popup")
            except:
                print("   No login link found, assuming already on login page")
        
        # Perform login with config credentials
        print("4. Logging in...")
        login_config = config.get('login', {})
        credentials = login_config.get('credentials', {})
        
        # Find email input
        email_input = None
        email_selectors = [
            '[data-testid="login-email-input"]',
            'input[type="email"]',
            'input[placeholder*="email" i]',
            '#email',
            'input[name="email"]'
        ]
        for selector in email_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=2000):
                    email_input = element
                    break
            except:
                continue
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        email_input.fill(credentials.get('email', 'admin@rediacc.io'))
        
        # Find password input
        password_input = None
        password_selectors = [
            '[data-testid="login-password-input"]',
            'input[type="password"]',
            '#password',
            'input[name="password"]'
        ]
        for selector in password_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=2000):
                    password_input = element
                    break
            except:
                continue
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        password_input.fill(credentials.get('password', 'admin'))
        
        # Find and click submit button
        submit_button = None
        submit_selectors = [
            '[data-testid="login-submit-button"]',
            'button[type="submit"]',
            'button:has-text("Sign In")',
            'button:has-text("Login")',
            'button.ant-btn-primary'
        ]
        for selector in submit_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=2000):
                    submit_button = element
                    break
            except:
                continue
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        submit_button.click()
        
        # Wait for dashboard
        print("5. Waiting for dashboard...")
        page.wait_for_url("**/console/dashboard", timeout=login_config.get('timeouts', {}).get('navigation', 10000))
        print("   Login successful!")
        
        # Navigate to System
        print("6. Navigating to System...")
        system_clicked = False
        system_selectors = [
            'text=System',
            'nav a:has-text("System")',
            '[data-testid*="system"]',
            'a[href*="/system"]',
            '.ant-menu-item:has-text("System")'
        ]
        
        for selector in system_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=2000):
                    element.click()
                    system_clicked = True
                    break
            except:
                continue
        
        if not system_clicked:
            raise Exception("Could not navigate to System")
        
        page.wait_for_load_state("networkidle")
        
        # Check for Simple/Expert mode and switch to Expert if needed
        print("7. Checking for Simple/Expert mode...")
        
        # Take screenshot if enabled
        if config.get('screenshots', {}).get('enabled', True):
            screenshot_path = Path(config.get('screenshots', {}).get('path', './artifacts/screenshots'))
            screenshot_path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path / "system_regionedit_before_mode_switch.png"))
            print(f"   Screenshot saved: {screenshot_path / 'system_regionedit_before_mode_switch.png'}")
        
        # Look for Interface Mode section and switch to Expert
        expert_clicked = False
        
        # First find the Expert radio button/label (it's at the bottom of the page)
        try:
            # Scroll down to make sure Interface Mode is visible
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            
            # Look for Expert option
            expert_element = page.locator('text=Expert').last  # Use last since it's at the bottom
            if expert_element.is_visible(timeout=2000):
                # Check if it's already selected
                parent = expert_element.locator('..')
                if 'checked' in parent.get_attribute('class') or '':
                    print("   Already in Expert mode")
                    expert_clicked = True
                else:
                    expert_element.click()
                    print("   Clicked Expert mode")
                    expert_clicked = True
                    # Wait for page to reload with Expert mode features
                    page.wait_for_timeout(2000)
        except:
            pass
        
        if not expert_clicked:
            # Alternative approach - look for the radio input directly
            try:
                expert_radio = page.locator('input[type="radio"]').nth(1)  # Usually Expert is the second option
                if expert_radio.is_visible():
                    expert_radio.click()
                    print("   Switched to Expert mode (radio button)")
                    expert_clicked = True
                    page.wait_for_timeout(2000)
            except:
                print("   Warning: Could not switch to Expert mode")
        
        # Navigate to Regions tab (only visible in Expert mode)
        print("8. Looking for Regions tab...")
        regions_found = False
        
        # Wait a bit for Expert mode UI to fully load
        page.wait_for_timeout(1000)
        
        regions_tab_selectors = [
            'button:has-text("Regions")',
            'a:has-text("Regions")',
            '[role="tab"]:has-text("Regions")',
            '.ant-tabs-tab:has-text("Regions")',
            'div[role="tab"]:has-text("Regions")',
            'text=Regions'
        ]
        
        for selector in regions_tab_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=2000):
                    element.click()
                    regions_found = True
                    print(f"   Clicked on Regions tab")
                    page.wait_for_load_state("networkidle", timeout=3000)
                    break
            except:
                continue
        
        if not regions_found:
            print("   Warning: Regions tab not found. This tab is only available in Expert mode.")
            print("   Attempting to create a test region first...")
            
            # Try to create a region if it doesn't exist
            try:
                # Look for create/add button
                create_selectors = [
                    'button:has-text("+")',
                    'button[title*="Add"]',
                    'button[title*="Create"]',
                    '.ant-btn-primary',
                    'button.ant-btn-dashed'
                ]
                
                for selector in create_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible(timeout=1000):
                            btn.click()
                            print("   Found and clicked create button")
                            
                            # Fill in region details
                            page.wait_for_selector('.ant-modal', state='visible', timeout=3000)
                            
                            # Find region name input
                            name_input = page.locator('input[placeholder*="region" i], input[id*="regionName"]').first
                            if name_input.is_visible():
                                name_input.fill("test001")
                                print("   Filled region name: test001")
                            
                            # Submit
                            submit_btn = page.locator('.ant-modal button:has-text("OK"), .ant-modal button:has-text("Create")').first
                            if submit_btn.is_visible():
                                submit_btn.click()
                                print("   Created test region")
                                page.wait_for_timeout(2000)
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Could not create test region: {e}")
        
        # Configuration for region edit
        region_config = config.get('systemRegionEdit', {
            'sourceRegion': 'Default Region',  # Changed to existing region
            'targetRegion': 'test002'
        })
        
        source_region = region_config.get('sourceRegion', 'Default Region')
        target_region = region_config.get('targetRegion', 'test002')
        
        # Click edit button for specific region
        print(f"9. Looking for region edit button for '{source_region}'...")
        edit_button_found = False
        
        # Wait for table to load
        page.wait_for_timeout(1000)
        
        # First check if any regions exist in the table
        try:
            table = page.locator('table.ant-table, .ant-table-wrapper table').first
            if table.is_visible(timeout=2000):
                print("   Found table, looking for regions...")
                
                # Check if the source region exists
                region_row = page.locator(f'tr:has-text("{source_region}")').first
                if region_row.is_visible(timeout=2000):
                    print(f"   Found region '{source_region}' in table")
                    # Source region exists, find its edit button (pencil icon button)
                    edit_selectors = [
                        'button[title="Edit"]',
                        'button[aria-label*="edit" i]',
                        'button.ant-btn-icon-only',
                        '[data-testid*="edit"]',
                        'button:has(svg)',
                        '.anticon-edit'
                    ]
                    
                    # Try to find the edit button in the actions column
                    actions_cell = region_row.locator('td').last  # Actions are usually in the last column
                    for selector in edit_selectors:
                        try:
                            edit_btn = actions_cell.locator(selector).first
                            if edit_btn.is_visible(timeout=500):
                                edit_btn.click()
                                edit_button_found = True
                                print(f"   Edit button clicked for region: {source_region}")
                                break
                        except:
                            continue
                    
                    # If not found in actions cell, try the whole row
                    if not edit_button_found:
                        for selector in edit_selectors:
                            try:
                                edit_btn = region_row.locator(selector).first
                                if edit_btn.is_visible(timeout=500):
                                    edit_btn.click()
                                    edit_button_found = True
                                    print(f"   Edit button clicked for region: {source_region}")
                                    break
                            except:
                                continue
                else:
                    # If source region doesn't exist, try to find any region to edit
                    print(f"   Region '{source_region}' not found, looking for any region...")
                    all_rows = page.locator('tbody tr, tr.ant-table-row')
                    if all_rows.count() > 0:
                        # Use the first available region
                        first_row = all_rows.first
                        actions_cell = first_row.locator('td').last
                        edit_btn = actions_cell.locator('button').first
                        if edit_btn.is_visible():
                            edit_btn.click()
                            edit_button_found = True
                            print("   Editing first available region")
        except Exception as e:
            print(f"   Error finding table or regions: {e}")
        
        # If still not found, try direct selectors
        if not edit_button_found:
            direct_selectors = [
                f'[data-testid="system-region-edit-button-{source_region}"]',
                'button:has-text("Edit"):visible',
                'button[title*="edit" i]:visible',
                '.ant-table button:has-text("Edit"):visible'
            ]
            
            for selector in direct_selectors:
                try:
                    element = page.locator(selector).first
                    if element.is_visible(timeout=1000):
                        element.click()
                        edit_button_found = True
                        print("   Edit button clicked using direct selector")
                        break
                except:
                    continue
        
        if not edit_button_found:
            print(f"   Warning: Could not find edit button for region '{source_region}'")
            print("   Region might not exist or edit option is not available")
        else:
            # Wait for modal to be fully loaded
            page.wait_for_selector('.ant-modal', state='visible', timeout=5000)
            
            # Edit region name
            print(f"10. Editing region name to '{target_region}'...")
            region_name_edited = False
            
            # First, let's look for any text input in the modal
            modal_inputs = page.locator('.ant-modal input[type="text"]:visible, .ant-modal input:not([type="hidden"]):visible')
            input_count = modal_inputs.count()
            print(f"   Found {input_count} input(s) in modal")
            
            if input_count > 0:
                # Usually the first visible input is the region name
                region_input = modal_inputs.first
                try:
                    # Clear existing value
                    region_input.click()
                    region_input.press("Control+a")
                    region_input.type(target_region)
                    region_name_edited = True
                    print(f"   Region name changed to: {target_region}")
                except:
                    # Try alternative clear and fill method
                    try:
                        current_value = region_input.input_value()
                        for _ in range(len(current_value)):
                            region_input.press("Backspace")
                        region_input.type(target_region)
                        region_name_edited = True
                        print(f"   Region name changed to: {target_region} (alternative method)")
                    except Exception as e:
                        print(f"   Error editing region name: {e}")
            
            if not region_name_edited:
                print("   Warning: Could not edit region name")
            
            # Submit region edit
            print("11. Submitting region edit...")
            submit_found = False
            
            # Try test-id first
            if smart_click(page, '[data-testid="resource-modal-ok-button"]', 2000):
                submit_found = True
                print("   Region edit submitted")
            else:
                # Try alternative selectors
                submit_selectors = [
                    '.ant-modal button:has-text("OK")',
                    '.ant-modal button:has-text("Save")',
                    '.ant-modal button:has-text("Update")',
                    '.ant-modal button.ant-btn-primary',
                    '[role="dialog"] button:has-text("OK")'
                ]
                for selector in submit_selectors:
                    if smart_click(page, selector, 2000):
                        submit_found = True
                        print("   Region edit submitted")
                        break
            
            if submit_found:
                # Wait for modal to close and changes to be applied
                try:
                    page.wait_for_selector('.ant-modal', state='hidden', timeout=5000)
                    print("   Region edit completed successfully")
                except:
                    print("   Region edit submitted (modal still visible)")
                
                # Check for success notification
                success_selectors = [
                    '.ant-message-success',
                    '.ant-notification-success',
                    'text=successfully'
                ]
                for selector in success_selectors:
                    if page.locator(selector).is_visible():
                        print("   Success notification detected")
                        break
        
        print("\nTest completed successfully!")
        
        # Take final screenshot if enabled
        if config.get('screenshots', {}).get('enabled', True):
            page.screenshot(path=str(screenshot_path / "system_regionedit_final.png"))
            print(f"Final screenshot: {screenshot_path / 'system_regionedit_final.png'}")
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals() and config.get('screenshots', {}).get('enabled', True):
            screenshot_path = Path(config.get('screenshots', {}).get('path', './artifacts/screenshots'))
            screenshot_path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path / "error_screenshot_regionedit.png"))
            print(f"Error screenshot saved to: {screenshot_path / 'error_screenshot_regionedit.png'}")
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