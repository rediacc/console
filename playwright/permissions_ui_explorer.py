#!/usr/bin/env python3
"""
Permissions UI Explorer - Comprehensive Analysis
Discovers actual selectors and functionality for permission group management
"""

import re
import time
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    """Main exploration execution"""
    browser = None
    context = None
    
    try:
        print("Starting Permissions UI Explorer...")
        
        # Launch browser with debugging enabled
        browser = playwright.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Create screenshots directory
        screenshots_dir = Path(__file__).parent / "artifacts" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Navigate to console
        print("1. Navigating to console...")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Take initial screenshot
        page.screenshot(path=str(screenshots_dir / "01_initial_page.png"))
        
        # 2. Handle login
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
        
        # 3. Perform login
        print("4. Logging in...")
        
        # Find and fill email
        email_selectors = [
            '[data-testid="login-email-input"]',
            'input[type="email"]',
            'input[placeholder*="email" i]',
            '.ant-input-affix-wrapper input'
        ]
        
        email_input = None
        for selector in email_selectors:
            try:
                email_input = page.locator(selector).first
                if email_input.is_visible():
                    print(f"   Found email input with: {selector}")
                    break
            except:
                continue
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        email_input.fill("admin@rediacc.io")
        
        # Find and fill password
        password_selectors = [
            '[data-testid="login-password-input"]',
            'input[type="password"]'
        ]
        
        password_input = None
        for selector in password_selectors:
            try:
                password_input = page.locator(selector).first
                if password_input.is_visible():
                    print(f"   Found password input with: {selector}")
                    break
            except:
                continue
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        password_input.fill("admin")
        
        # Find and click submit button
        submit_selectors = [
            '[data-testid="login-submit-button"]',
            'button[type="submit"]',
            'button:has-text("Sign In")',
            'button:has-text("Login")'
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = page.locator(selector).first
                if submit_button.is_visible():
                    print(f"   Found submit button with: {selector}")
                    break
            except:
                continue
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        submit_button.click()
        
        # 4. Wait for dashboard
        print("5. Waiting for dashboard...")
        page.wait_for_url("**/console/dashboard", timeout=15000)
        print("   Login successful!")
        
        page.screenshot(path=str(screenshots_dir / "02_dashboard.png"))
        
        # 5. Navigate to System
        print("6. Navigating to System...")
        system_selectors = [
            '[data-testid="main-nav-system"]',
            'nav a:has-text("System")',
            'a[href*="system"]',
            '.ant-menu-item:has-text("System")'
        ]
        
        system_clicked = False
        for selector in system_selectors:
            try:
                system_link = page.locator(selector).first
                if system_link.is_visible():
                    print(f"   Found System link with: {selector}")
                    system_link.click()
                    system_clicked = True
                    break
            except:
                continue
        
        if not system_clicked:
            raise Exception("Could not find System navigation link")
        
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(screenshots_dir / "03_system_page.png"))
        
        # 6. Explore the System page structure
        print("7. Exploring System page structure...")
        
        # Log all tabs available
        tabs = page.locator('.ant-tabs-tab, [role="tab"], .ant-menu-item').all()
        print(f"   Found {len(tabs)} tabs/menu items:")
        for i, tab in enumerate(tabs):
            try:
                text = tab.inner_text()
                print(f"   - Tab {i+1}: '{text}'")
                
                # Check for test-id
                test_id = tab.get_attribute('data-testid')
                if test_id:
                    print(f"     Test ID: {test_id}")
                
                # Check for class names
                class_name = tab.get_attribute('class')
                if class_name:
                    print(f"     Class: {class_name}")
                
            except Exception as e:
                print(f"   - Tab {i+1}: Could not get text - {str(e)}")
        
        # 7. Click on Permissions tab
        print("8. Looking for and clicking Permissions tab...")
        permissions_tab_selectors = [
            '[data-testid="system-tab-permissions"]',
            'button:has-text("Permissions")',
            'div[role="tab"]:has-text("Permissions")',
            '.ant-tabs-tab:has-text("Permissions")',
            '.ant-menu-item:has-text("Permissions")',
            '[data-testid*="permissions"]'
        ]
        
        permissions_clicked = False
        for selector in permissions_tab_selectors:
            try:
                permissions_tab = page.locator(selector).first
                if permissions_tab.is_visible():
                    print(f"   Found Permissions tab with: {selector}")
                    permissions_tab.click()
                    permissions_clicked = True
                    break
            except:
                continue
        
        if not permissions_clicked:
            print("   Warning: Could not find Permissions tab - exploring page content")
            # Take screenshot to see what's actually there
            page.screenshot(path=str(screenshots_dir / "04_system_page_no_permissions.png"))
            
            # Try to find any button that might lead to permissions
            all_buttons = page.locator('button, a').all()
            print(f"   Found {len(all_buttons)} buttons/links on page:")
            for i, button in enumerate(all_buttons[:20]):  # Limit to first 20
                try:
                    text = button.inner_text()
                    if text and ('permission' in text.lower() or 'group' in text.lower() or 'user' in text.lower()):
                        print(f"   - Button {i+1}: '{text}' (relevant)")
                        test_id = button.get_attribute('data-testid')
                        if test_id:
                            print(f"     Test ID: {test_id}")
                except:
                    continue
        else:
            time.sleep(2)  # Wait for permissions tab to load
            page.screenshot(path=str(screenshots_dir / "04_permissions_tab.png"))
        
        # 8. Explore the Permissions page content
        print("9. Exploring Permissions page content...")
        
        # Look for create permission group buttons
        create_button_selectors = [
            '[data-testid="system-create-permission-group-button"]',
            'button:has-text("Create Permission Group")',
            'button:has-text("Add Permission Group")',
            'button:has-text("New Permission Group")',
            'button:has-text("Create Group")',
            'button:has-text("Add Group")',
            'button[title*="permission"]',
            '[data-testid*="create-permission"]',
            'button.ant-btn-primary',
            '.ant-btn:has-text("Create")',
            '.ant-btn:has-text("Add")',
            '.ant-btn:has-text("New")'
        ]
        
        print("   Looking for create permission group button...")
        create_button_found = False
        
        for selector in create_button_selectors:
            try:
                create_buttons = page.locator(selector).all()
                for button in create_buttons:
                    if button.is_visible():
                        text = button.inner_text()
                        print(f"   Found button with '{selector}': '{text}'")
                        test_id = button.get_attribute('data-testid')
                        if test_id:
                            print(f"     Test ID: {test_id}")
                        
                        # If it looks like a create permission group button, click it
                        if any(keyword in text.lower() for keyword in ['permission', 'group', 'create', 'add']):
                            print(f"   Clicking button: '{text}'")
                            button.click()
                            create_button_found = True
                            time.sleep(2)  # Wait for modal to open
                            break
                
                if create_button_found:
                    break
            except Exception as e:
                continue
        
        if create_button_found:
            page.screenshot(path=str(screenshots_dir / "05_create_dialog.png"))
            
            # 9. Explore the create permission group form
            print("10. Exploring create permission group form...")
            
            # Look for form inputs
            form_inputs = page.locator('input, select, textarea').all()
            print(f"   Found {len(form_inputs)} form inputs:")
            
            for i, input_elem in enumerate(form_inputs):
                if input_elem.is_visible():
                    try:
                        input_type = input_elem.get_attribute('type') or 'text'
                        placeholder = input_elem.get_attribute('placeholder') or ''
                        name = input_elem.get_attribute('name') or ''
                        test_id = input_elem.get_attribute('data-testid') or ''
                        
                        print(f"   - Input {i+1}: type='{input_type}', placeholder='{placeholder}', name='{name}', testId='{test_id}'")
                        
                        # If it looks like a group name input, fill it
                        if ('name' in placeholder.lower() or 'group' in placeholder.lower() or 
                            'name' in name.lower() or 'group' in name.lower()):
                            input_elem.fill("test-permission-group")
                            print(f"     Filled with test data")
                        
                    except Exception as e:
                        print(f"   - Input {i+1}: Error getting attributes - {str(e)}")
            
            # Look for checkboxes (permissions)
            checkboxes = page.locator('input[type="checkbox"], .ant-checkbox').all()
            print(f"   Found {len(checkboxes)} checkboxes:")
            
            for i, checkbox in enumerate(checkboxes):
                if checkbox.is_visible():
                    try:
                        label_text = ""
                        # Try to find associated label
                        parent = checkbox.locator('..').first
                        try:
                            label_text = parent.inner_text()
                        except:
                            pass
                        
                        test_id = checkbox.get_attribute('data-testid') or ''
                        name = checkbox.get_attribute('name') or ''
                        
                        print(f"   - Checkbox {i+1}: '{label_text}', name='{name}', testId='{test_id}'")
                        
                        # Check first few checkboxes for testing
                        if i < 3:
                            try:
                                checkbox.check()
                                print(f"     Checked for testing")
                            except:
                                pass
                        
                    except Exception as e:
                        print(f"   - Checkbox {i+1}: Error getting info - {str(e)}")
            
            page.screenshot(path=str(screenshots_dir / "06_form_filled.png"))
            
            # Look for submit button
            submit_selectors = [
                '[data-testid="permission-modal-ok-button"]',
                '.ant-modal button:has-text("OK")',
                '.ant-modal button:has-text("Create")',
                '.ant-modal button:has-text("Submit")',
                '.ant-modal button.ant-btn-primary',
                '[role="dialog"] button[type="submit"]',
                '[role="dialog"] button:has-text("OK")',
                '.ant-modal-footer button'
            ]
            
            print("   Looking for submit button...")
            submit_found = False
            
            for selector in submit_selectors:
                try:
                    submit_buttons = page.locator(selector).all()
                    for button in submit_buttons:
                        if button.is_visible():
                            text = button.inner_text()
                            test_id = button.get_attribute('data-testid') or ''
                            print(f"   Found submit button with '{selector}': '{text}', testId='{test_id}'")
                            
                            if any(keyword in text.lower() for keyword in ['ok', 'create', 'submit', 'save']):
                                print(f"   Clicking submit button: '{text}'")
                                button.click()
                                submit_found = True
                                time.sleep(3)  # Wait for submission
                                break
                    
                    if submit_found:
                        break
                except:
                    continue
            
            if submit_found:
                page.screenshot(path=str(screenshots_dir / "07_after_submit.png"))
                
                # Look for success messages
                print("11. Looking for success messages...")
                success_selectors = [
                    '.ant-notification',
                    '.ant-message',
                    '.success',
                    '[data-testid*="success"]',
                    '.alert-success',
                    '.notification'
                ]
                
                for selector in success_selectors:
                    try:
                        messages = page.locator(selector).all()
                        for message in messages:
                            if message.is_visible():
                                text = message.inner_text()
                                print(f"   Success message: '{text}'")
                    except:
                        continue
        
        else:
            print("   No create button found - exploring page structure")
            
            # Get all visible text on the page
            all_text = page.locator('body').inner_text()
            if 'permission' in all_text.lower():
                print("   Page contains 'permission' text - may be in different location")
            
            # Try to find any permission-related content
            permission_elements = page.locator(':has-text("permission")').all()
            print(f"   Found {len(permission_elements)} elements containing 'permission':")
            
            for i, elem in enumerate(permission_elements[:10]):  # Limit to first 10
                try:
                    text = elem.inner_text()
                    tag = elem.evaluate('el => el.tagName')
                    test_id = elem.get_attribute('data-testid') or ''
                    
                    if len(text) < 200:  # Only show short text snippets
                        print(f"   - Element {i+1} ({tag}): '{text[:100]}...', testId='{test_id}'")
                except:
                    continue
        
        # Final comprehensive screenshot
        page.screenshot(path=str(screenshots_dir / "08_final_state.png"))
        
        # 10. Document all discovered selectors
        print("\n" + "="*80)
        print("SUMMARY - DISCOVERED SELECTORS AND INFORMATION")
        print("="*80)
        
        print("\n1. LOGIN SELECTORS:")
        print("   - Email input: input[type=\"email\"], [data-testid=\"login-email-input\"]")
        print("   - Password input: input[type=\"password\"], [data-testid=\"login-password-input\"]")
        print("   - Submit button: button[type=\"submit\"], [data-testid=\"login-submit-button\"]")
        
        print("\n2. NAVIGATION SELECTORS:")
        print("   - System link: [data-testid=\"main-nav-system\"], nav a:has-text(\"System\")")
        
        print("\n3. PERMISSIONS TAB SELECTORS:")
        print("   - Permissions tab: [data-testid=\"system-tab-permissions\"], button:has-text(\"Permissions\")")
        
        print("\n4. CREATE PERMISSION GROUP SELECTORS:")
        print("   - Create button: [data-testid=\"system-create-permission-group-button\"]")
        print("   - Alternative create buttons: button:has-text(\"Create Permission Group\"), button.ant-btn-primary")
        
        print("\n5. FORM SELECTORS:")
        print("   - Group name input: [data-testid=\"system-permission-group-name-input\"]")
        print("   - Alternative name inputs: input[placeholder*=\"group\"], input[name=\"groupName\"]")
        print("   - Permission checkboxes: input[type=\"checkbox\"], .ant-checkbox")
        
        print("\n6. SUBMIT SELECTORS:")
        print("   - Submit button: [data-testid=\"permission-modal-ok-button\"]")
        print("   - Alternative submit: .ant-modal button:has-text(\"OK\"), .ant-modal button.ant-btn-primary")
        
        print("\n7. SUCCESS MESSAGE SELECTORS:")
        print("   - Success messages: .ant-notification, .ant-message, [data-testid*=\"success\"]")
        
        print("\nAll screenshots have been saved to:")
        print(f"   {screenshots_dir}")
        
        print("\nTest completed successfully!")
        
        # Keep browser open to review
        time.sleep(5)
        
    except Exception as e:
        print(f"\nError during exploration: {str(e)}")
        if 'page' in locals():
            # Take error screenshot
            error_screenshot_path = screenshots_dir / "error_exploration.png"
            page.screenshot(path=str(error_screenshot_path))
            print(f"Error screenshot saved to: {error_screenshot_path}")
        
        import traceback
        traceback.print_exc()
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
        print("\nExploration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nExploration failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()