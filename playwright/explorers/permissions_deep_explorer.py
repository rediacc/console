#!/usr/bin/env python3
"""
Deep Permissions UI Explorer
Explores the actual permission group structure and creation workflow
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
        print("Starting Deep Permissions UI Explorer...")
        
        # Launch browser with debugging enabled
        browser = playwright.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Create screenshots directory
        screenshots_dir = Path(__file__).parent / "artifacts" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Navigate and login (simplified since we know the selectors)
        print("1. Navigating to console and logging in...")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Login
        page.locator('[data-testid="login-email-input"]').fill("admin@rediacc.io")
        page.locator('[data-testid="login-password-input"]').fill("admin")
        page.locator('[data-testid="login-submit-button"]').click()
        
        page.wait_for_url("**/console/dashboard", timeout=15000)
        print("   Login successful!")
        
        # 2. Navigate to System
        print("2. Navigating to System...")
        page.locator('[data-testid="main-nav-system"]').click()
        page.wait_for_load_state("networkidle")
        
        page.screenshot(path=str(screenshots_dir / "01_system_page.png"))
        
        # 3. Look for tabs and explore the structure
        print("3. Exploring System tabs...")
        
        # Check for tabs
        tabs = page.locator('.ant-tabs-tab').all()
        print(f"   Found {len(tabs)} tabs:")
        for i, tab in enumerate(tabs):
            try:
                text = tab.inner_text()
                print(f"   - Tab {i+1}: '{text}'")
            except:
                print(f"   - Tab {i+1}: Could not get text")
        
        # 4. Look for permission-related buttons in Users section
        print("4. Looking for permission-related functionality...")
        
        # Look for permission buttons for users
        permission_buttons = page.locator('button[data-testid*="permissions"]').all()
        print(f"   Found {len(permission_buttons)} permission buttons:")
        
        for i, button in enumerate(permission_buttons):
            try:
                test_id = button.get_attribute('data-testid')
                print(f"   - Button {i+1}: {test_id}")
                
                # Click the first permissions button to open the modal
                if i == 0:
                    print(f"   Clicking first permission button...")
                    button.click()
                    time.sleep(2)
                    
                    page.screenshot(path=str(screenshots_dir / "02_permissions_modal.png"))
                    
                    # Explore the permissions modal
                    print("5. Exploring permissions modal...")
                    
                    # Look for permission group dropdown
                    dropdown = page.locator('.ant-select-selector').first
                    if dropdown.is_visible():
                        print("   Found permission group dropdown")
                        dropdown.click()
                        time.sleep(1)
                        
                        page.screenshot(path=str(screenshots_dir / "03_dropdown_open.png"))
                        
                        # Look for dropdown options
                        options = page.locator('.ant-select-item').all()
                        print(f"   Found {len(options)} dropdown options:")
                        
                        for j, option in enumerate(options):
                            try:
                                text = option.inner_text()
                                print(f"   - Option {j+1}: '{text}'")
                            except:
                                print(f"   - Option {j+1}: Could not get text")
                        
                        # Look for "Create Group" or "Add Group" option
                        create_group_option = None
                        for option in options:
                            try:
                                text = option.inner_text()
                                if any(keyword in text.lower() for keyword in ['create', 'add', 'new', '+']):
                                    print(f"   Found potential create option: '{text}'")
                                    create_group_option = option
                                    break
                            except:
                                continue
                        
                        if create_group_option:
                            print("   Clicking create group option...")
                            create_group_option.click()
                            time.sleep(2)
                            
                            page.screenshot(path=str(screenshots_dir / "04_create_group_clicked.png"))
                            
                            # Look for create group form
                            print("6. Looking for create group form...")
                            
                            # Check for new modal or form
                            modal_content = page.locator('.ant-modal-content').all()
                            print(f"   Found {len(modal_content)} modal content areas")
                            
                            # Look for input fields in any modal
                            inputs = page.locator('.ant-modal input').all()
                            print(f"   Found {len(inputs)} input fields in modals:")
                            
                            for k, input_elem in enumerate(inputs):
                                try:
                                    placeholder = input_elem.get_attribute('placeholder') or ''
                                    name = input_elem.get_attribute('name') or ''
                                    test_id = input_elem.get_attribute('data-testid') or ''
                                    
                                    print(f"   - Input {k+1}: placeholder='{placeholder}', name='{name}', testId='{test_id}'")
                                    
                                    # Fill group name if it looks like a group name field
                                    if any(keyword in placeholder.lower() + name.lower() + test_id.lower() 
                                          for keyword in ['group', 'name']):
                                        input_elem.fill("Test Permission Group")
                                        print(f"     Filled with: 'Test Permission Group'")
                                        
                                except Exception as e:
                                    print(f"   - Input {k+1}: Error - {str(e)}")
                            
                            page.screenshot(path=str(screenshots_dir / "05_form_filled.png"))
                            
                            # Look for checkboxes or permission selection
                            checkboxes = page.locator('.ant-modal input[type="checkbox"]').all()
                            print(f"   Found {len(checkboxes)} checkboxes in modal:")
                            
                            checkbox_count = 0
                            for checkbox in checkboxes:
                                if checkbox.is_visible() and checkbox_count < 3:
                                    try:
                                        # Find label text
                                        parent = checkbox.locator('..').first
                                        label_text = parent.inner_text()
                                        
                                        print(f"   - Checkbox: '{label_text}'")
                                        checkbox.check()
                                        checkbox_count += 1
                                        
                                    except Exception as e:
                                        print(f"   - Checkbox: Error - {str(e)}")
                            
                            page.screenshot(path=str(screenshots_dir / "06_checkboxes_selected.png"))
                            
                            # Look for submit button
                            print("7. Looking for submit button...")
                            submit_buttons = page.locator('.ant-modal button').all()
                            
                            for button in submit_buttons:
                                try:
                                    text = button.inner_text()
                                    test_id = button.get_attribute('data-testid') or ''
                                    
                                    if any(keyword in text.lower() for keyword in ['ok', 'create', 'save', 'submit']):
                                        print(f"   Found submit button: '{text}' (testId: {test_id})")
                                        button.click()
                                        time.sleep(3)
                                        
                                        page.screenshot(path=str(screenshots_dir / "07_after_submit.png"))
                                        
                                        # Look for success message
                                        success_messages = page.locator('.ant-notification, .ant-message').all()
                                        for msg in success_messages:
                                            if msg.is_visible():
                                                try:
                                                    text = msg.inner_text()
                                                    print(f"   Success message: '{text}'")
                                                except:
                                                    pass
                                        break
                                except:
                                    continue
                        
                        else:
                            print("   No create group option found")
                            
                            # Close dropdown and explore other areas
                            page.keyboard.press('Escape')
                            time.sleep(1)
                            
                            # Cancel the modal
                            cancel_button = page.locator('button:has-text("Cancel")').first
                            if cancel_button.is_visible():
                                cancel_button.click()
                                time.sleep(1)
                    
                    break  # Only click first permission button
                    
            except Exception as e:
                print(f"   - Button {i+1}: Error - {str(e)}")
        
        # 5. Look for other areas where permission groups might be managed
        print("8. Looking for other permission group management areas...")
        
        # Check Teams tab
        teams_tab = page.locator('.ant-tabs-tab:has-text("Teams")').first
        if teams_tab.is_visible():
            print("   Switching to Teams tab...")
            teams_tab.click()
            time.sleep(2)
            
            page.screenshot(path=str(screenshots_dir / "08_teams_tab.png"))
            
            # Look for permission-related functionality in Teams
            team_permission_buttons = page.locator('button[data-testid*="permission"]').all()
            print(f"   Found {len(team_permission_buttons)} permission buttons in Teams:")
            
            for button in team_permission_buttons:
                try:
                    test_id = button.get_attribute('data-testid')
                    text = button.inner_text()
                    print(f"   - Team permission button: {test_id} - '{text}'")
                except:
                    continue
        
        # 6. Look for a dedicated Permission Groups section
        print("9. Looking for dedicated Permission Groups management...")
        
        # Check if there are other navigation items
        nav_items = page.locator('[data-testid*="nav"], .ant-menu-item').all()
        for item in nav_items:
            try:
                text = item.inner_text()
                if 'permission' in text.lower():
                    print(f"   Found navigation item with permissions: '{text}'")
            except:
                continue
        
        # Look for any buttons with "Create" in them
        create_buttons = page.locator('button:has-text("Create"), button:has-text("Add"), button:has-text("New")').all()
        print(f"   Found {len(create_buttons)} create/add buttons:")
        
        for button in create_buttons:
            try:
                text = button.inner_text()
                test_id = button.get_attribute('data-testid') or ''
                
                if any(keyword in text.lower() for keyword in ['permission', 'group']):
                    print(f"   - Relevant create button: '{text}' (testId: {test_id})")
                else:
                    print(f"   - Create button: '{text}' (testId: {test_id})")
                    
            except:
                continue
        
        page.screenshot(path=str(screenshots_dir / "09_final_exploration.png"))
        
        # 7. Document findings
        print("\n" + "="*80)
        print("DEEP EXPLORATION RESULTS - PERMISSION GROUPS")
        print("="*80)
        
        print("\n1. SYSTEM NAVIGATION:")
        print("   - System page: [data-testid='main-nav-system']")
        print("   - Default view: Users tab with permission management per user")
        
        print("\n2. PERMISSION ASSIGNMENT WORKFLOW:")
        print("   - Individual user permissions: button[data-testid*='permissions']")
        print("   - Opens modal: 'Assign Permissions - [user email]'")
        print("   - Permission Group dropdown: .ant-select-selector")
        print("   - Modal buttons: Cancel, Assign")
        
        print("\n3. PERMISSION GROUPS DISCOVERED:")
        print("   - 'Administrators' group exists (visible in dropdown)")
        print("   - Shows format: 'Group Name (X users, Y permissions)'")
        print("   - Dropdown selector: .ant-select-item")
        
        print("\n4. POTENTIAL CREATE GROUP WORKFLOW:")
        print("   - May be accessible through permission group dropdown")
        print("   - Look for options like 'Create New Group' or '+' in dropdown")
        print("   - Form fields likely: group name input, permission checkboxes")
        
        print("\n5. KEY TEST-IDS FOUND:")
        print("   - User permission button: system-user-permissions-button-[email]")
        print("   - Modal assign button: modal-assign-permissions-ok")
        print("   - Various system buttons with descriptive test-ids")
        
        print("\n6. ACTUAL SELECTORS TO USE:")
        print("   - Permission modal trigger: [data-testid*='user-permissions-button']")
        print("   - Permission group dropdown: .ant-select-selector")
        print("   - Dropdown options: .ant-select-item")
        print("   - Modal submit: button:has-text('Assign')")
        print("   - Modal cancel: button:has-text('Cancel')")
        
        print(f"\nScreenshots saved to: {screenshots_dir}")
        
        time.sleep(5)  # Keep browser open
        
    except Exception as e:
        print(f"\nError during deep exploration: {str(e)}")
        if 'page' in locals():
            error_screenshot_path = screenshots_dir / "error_deep_exploration.png"
            page.screenshot(path=str(error_screenshot_path))
            print(f"Error screenshot saved to: {error_screenshot_path}")
        
        import traceback
        traceback.print_exc()
        raise
    
    finally:
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
        print("\nDeep exploration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nDeep exploration failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()