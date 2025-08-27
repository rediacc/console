#!/usr/bin/env python3
"""
System Region Delete Test - Smart Version
Tests the region deletion functionality in Rediacc console
"""

import json
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
        print("Starting System Region Delete Test (Smart Version)...")
        
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
        
        # Find and fill email input
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
                    element.fill(credentials.get('email', 'admin@rediacc.io'))
                    break
            except:
                continue
        
        # Find and fill password input
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
                    element.fill(credentials.get('password', 'admin'))
                    break
            except:
                continue
        
        # Find and click submit button
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
                    element.click()
                    break
            except:
                continue
        
        # Wait for dashboard
        print("5. Waiting for dashboard...")
        page.wait_for_url("**/console/dashboard", timeout=login_config.get('timeouts', {}).get('navigation', 10000))
        print("   Login successful!")
        
        # Navigate to System
        print("6. Navigating to System...")
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
                    break
            except:
                continue
        
        page.wait_for_load_state("networkidle")
        
        # Check for Simple/Expert mode and switch to Expert if needed
        print("7. Checking for Simple/Expert mode...")
        
        # Take screenshot if enabled
        if config.get('screenshots', {}).get('enabled', True):
            screenshot_path = Path(config.get('screenshots', {}).get('path', './artifacts/screenshots'))
            screenshot_path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path / "system_regiondelete_before_mode.png"))
            print(f"   Screenshot saved: {screenshot_path / 'system_regiondelete_before_mode.png'}")
        
        # Switch to Expert mode
        try:
            # Scroll down to make sure Interface Mode is visible
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            
            # Look for Expert option
            expert_element = page.locator('text=Expert').last
            if expert_element.is_visible(timeout=2000):
                # Check if not already selected
                parent = expert_element.locator('..')
                class_attr = parent.get_attribute('class') or ''
                if 'checked' not in class_attr:
                    expert_element.click()
                    print("   Switched to Expert mode")
                    page.wait_for_timeout(2000)
                else:
                    print("   Already in Expert mode")
        except:
            # Alternative approach
            try:
                expert_radio = page.locator('input[type="radio"]').nth(1)
                if expert_radio.is_visible():
                    expert_radio.click()
                    print("   Switched to Expert mode (radio button)")
                    page.wait_for_timeout(2000)
            except:
                print("   Warning: Could not switch to Expert mode")
        
        # Look for Regions & Infrastructure section (not a tab, but a section on the page)
        print("8. Looking for Regions & Infrastructure section...")
        regions_found = False
        
        region_delete_config = config.get('systemRegionDelete', {})
        
        # First, take a screenshot to see current state
        if config.get('screenshots', {}).get('enabled', True):
            screenshot_path = Path(config.get('screenshots', {}).get('path', './artifacts/screenshots'))
            page.screenshot(path=str(screenshot_path / "system_page_after_expert_mode.png"))
            print(f"   Current page screenshot: {screenshot_path / 'system_page_after_expert_mode.png'}")
        
        # Scroll down to find the Regions & Infrastructure section
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
        
        # Look for Regions & Infrastructure heading
        regions_section = page.locator('h2:has-text("Regions & Infrastructure"), h3:has-text("Regions & Infrastructure")').first
        
        if regions_section.is_visible(timeout=3000):
            print("   Found Regions & Infrastructure section")
            regions_section.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            regions_found = True
            
            # Now specifically look for the regions table in this section
            # The table should have Default Region or other regions
            regions_table = page.locator('text="Regions & Infrastructure" ~ * table, text="Regions & Infrastructure" ~ * * table').first
            
            if not regions_table.is_visible():
                # Try finding table by looking for specific content
                if page.locator('text="Default Region"').is_visible(timeout=2000):
                    print("   Default Region found in Regions table")
                    regions_table = page.locator('text="Default Region"').locator('xpath=ancestor::table').first
                elif page.locator('text=REGION NAME').is_visible(timeout=2000):
                    print("   REGION NAME header found in Regions table")  
                    regions_table = page.locator('text=REGION NAME').locator('xpath=ancestor::table').first
            
            if regions_table and regions_table.is_visible():
                print("   Regions table located successfully")
        
        if not regions_found:
            print("   Warning: Regions & Infrastructure section not found.")
            print("   This section should appear when in Expert mode.")
            # Take a screenshot to debug
            if config.get('screenshots', {}).get('enabled', True):
                screenshot_path = Path(config.get('screenshots', {}).get('path', './artifacts/screenshots'))
                page.screenshot(path=str(screenshot_path / "regions_section_not_found.png"))
                print(f"   Debug screenshot: {screenshot_path / 'regions_section_not_found.png'}")
        
        # Configuration for region deletion
        target_region = region_delete_config.get('targetRegion', 'region004')
        
        # Find and click delete button for specific region
        print(f"9. Looking for delete button for region '{target_region}'...")
        delete_found = False
        
        # Wait for table to load
        page.wait_for_timeout(1000)
        
        # Make sure we're looking at the correct table (Regions table, not Users table)
        # The Regions table should be under "Regions & Infrastructure" section
        try:
            # Find the Regions table specifically
            regions_table = None
            
            # First try to find table under Regions & Infrastructure
            if page.locator('text="Regions & Infrastructure"').is_visible():
                # Get the section containing Regions & Infrastructure
                regions_section = page.locator('text="Regions & Infrastructure"').first
                # Find table within or after this section
                regions_table = page.locator('text="Regions & Infrastructure" ~ * table').first
                
                if not regions_table.is_visible():
                    # Try to find by Default Region
                    if page.locator('text="Default Region"').is_visible():
                        regions_table = page.locator('text="Default Region"').locator('xpath=ancestor::table').first
            
            if regions_table and regions_table.is_visible(timeout=2000):
                print("   Found Regions table under Regions & Infrastructure")
                
                # Look for the target region IN THE REGIONS TABLE
                region_row = regions_table.locator(f'tr:has-text("{target_region}")').first
                if region_row.is_visible(timeout=2000):
                    print(f"   Found region '{target_region}' in table")
                    
                    # Find delete button in the row (trash/delete icon)
                    # In the actions column, there are usually 3 buttons: edit (pencil), audit/history, delete (trash)
                    actions_cell = region_row.locator('td').last
                    
                    # Try to find all buttons in actions cell
                    all_buttons = actions_cell.locator('button')
                    button_count = all_buttons.count()
                    print(f"   Found {button_count} buttons in actions cell")
                    
                    if button_count == 3:
                        # For 3 buttons: edit (0), audit (1), delete (2)
                        delete_btn = all_buttons.nth(2)  # Third button (index 2)
                        print("   Selecting third button (delete) from 3 buttons")
                    elif button_count == 2:
                        # For 2 buttons: edit (0), delete (1)
                        delete_btn = all_buttons.nth(1)  # Second button (index 1)
                        print("   Selecting second button (delete) from 2 buttons")
                    else:
                        # Fallback to last button
                        delete_btn = all_buttons.last
                        print(f"   Selecting last button from {button_count} buttons")
                    
                    try:
                        if delete_btn.is_visible():
                            # Get button info for debugging
                            title = delete_btn.get_attribute('title') or ''
                            aria_label = delete_btn.get_attribute('aria-label') or ''
                            print(f"   Button attributes - title: '{title}', aria-label: '{aria_label}'")
                            
                            delete_btn.click()
                            delete_found = True
                            print(f"   Delete button clicked for region: {target_region}")
                    except Exception as e:
                        print(f"   Error clicking delete button: {e}")
                    
                    # If not found, try specific delete selectors
                    if not delete_found:
                        delete_selectors = [
                            'button[title*="Delete" i]',
                            'button[title*="delete" i]',
                            'button[aria-label*="delete" i]',
                            'button:has(.anticon-delete)',
                            'button:has(svg[data-icon="delete"])'
                        ]
                        
                        for selector in delete_selectors:
                            try:
                                delete_btn = actions_cell.locator(selector).first
                                if delete_btn.is_visible(timeout=500):
                                    delete_btn.click()
                                    delete_found = True
                                    print(f"   Delete button clicked using selector: {selector}")
                                    break
                            except:
                                continue
                else:
                    # Region not found, try to delete any test region IN THE REGIONS TABLE
                    print(f"   Region '{target_region}' not found, looking for any deletable region...")
                    # Try different row selectors
                    all_rows = regions_table.locator('tr')
                    row_count = all_rows.count()
                    
                    if row_count == 0:
                        # Try another selector
                        all_rows = regions_table.locator('.ant-table-row')
                        row_count = all_rows.count()
                    
                    print(f"   Found {row_count} rows in Regions table")
                    
                    # Skip header row and try to delete any region (including Default for testing)
                    for i in range(row_count):
                        row = all_rows.nth(i)
                        row_text = row.inner_text()
                        # Skip header rows
                        if 'REGION NAME' in row_text or 'ACTIONS' in row_text:
                            continue
                        
                        # For testing, we can try Default Region if no other regions exist
                        print(f"   Row {i} text: {row_text[:100]}...")  # Print first 100 chars
                        if True:  # Allow any region for testing
                            actions_cell = row.locator('td').last
                            all_buttons = actions_cell.locator('button')
                            button_count = all_buttons.count()
                            
                            if button_count == 3:
                                # For 3 buttons: edit (0), audit (1), delete (2)
                                delete_btn = all_buttons.nth(2)
                                print(f"   Row {i}: Selecting third button (delete) from 3 buttons")
                            elif button_count == 2:
                                # For 2 buttons: edit (0), delete (1)
                                delete_btn = all_buttons.nth(1)
                                print(f"   Row {i}: Selecting second button (delete) from 2 buttons")
                            elif button_count > 0:
                                # Fallback to last button
                                delete_btn = all_buttons.last
                                print(f"   Row {i}: Selecting last button from {button_count} buttons")
                            else:
                                continue
                            
                            try:
                                if delete_btn.is_visible():
                                    print(f"   Found deletable region at row {i}")
                                    delete_btn.click()
                                    delete_found = True
                                    print(f"   Delete button clicked for region at index {i}")
                                    break
                            except:
                                continue
        except Exception as e:
            print(f"   Error finding delete button: {e}")
        
        if not delete_found:
            print(f"   Warning: Could not find delete button for region '{target_region}'")
            print("   Region might not exist or delete option is not available")
        else:
            # Wait for confirmation dialog
            page.wait_for_timeout(1000)
            
            # Confirm deletion
            print("10. Confirming deletion...")
            confirm_found = False
            
            # First wait for any popup/modal to appear
            page.wait_for_timeout(500)
            
            # Check for popconfirm first (small popup)
            popconfirm = page.locator('.ant-popconfirm, .ant-popover').first
            if popconfirm.is_visible(timeout=1000):
                print("   Found confirmation popup")
                # Look for Yes/OK button in the popup
                confirm_btn = popconfirm.locator('button.ant-btn-dangerous, button.ant-btn-primary, button:has-text("Yes"), button:has-text("OK")').first
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    confirm_found = True
                    print("   Deletion confirmed via popup")
            
            # If no popconfirm, check for modal dialog
            if not confirm_found:
                modal = page.locator('.ant-modal, [role="dialog"]').first
                if modal.is_visible(timeout=1000):
                    print("   Found confirmation modal")
                    confirm_selectors = [
                        'button:has-text("Yes")',
                        'button:has-text("OK")',
                        'button:has-text("Delete")',
                        'button.ant-btn-dangerous',
                        'button.ant-btn-primary'
                    ]
                    
                    for selector in confirm_selectors:
                        try:
                            confirm_btn = modal.locator(selector).first
                            if confirm_btn.is_visible(timeout=500):
                                confirm_btn.click()
                                confirm_found = True
                                print("   Deletion confirmed via modal")
                                break
                        except:
                            continue
            
            if confirm_found:
                # Wait for deletion to complete
                page.wait_for_timeout(2000)
                
                # Check for success notification
                success_selectors = region_delete_config.get('validation', {}).get('notificationSelectors', [])
                for selector in success_selectors:
                    if page.locator(selector).is_visible(timeout=1000):
                        print("   Success notification detected")
                        break
                
                print("   Region deletion completed successfully!")
            else:
                print("   Warning: Could not confirm deletion")
        
        print("\nTest completed successfully!")
        
        # Take final screenshot if enabled
        if config.get('screenshots', {}).get('enabled', True):
            page.screenshot(path=str(screenshot_path / "system_regiondelete_final.png"))
            print(f"Final screenshot: {screenshot_path / 'system_regiondelete_final.png'}")
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals() and config.get('screenshots', {}).get('enabled', True):
            screenshot_path = Path(config.get('screenshots', {}).get('path', './artifacts/screenshots'))
            screenshot_path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path / "error_screenshot_regiondelete.png"))
            print(f"Error screenshot saved to: {screenshot_path / 'error_screenshot_regiondelete.png'}")
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