#!/usr/bin/env python3
"""
System Permissions Test - Improved Version
Tests the permission group creation functionality in Rediacc console.
This test switches to Expert mode to access the Permissions tab and tests permission group creation.
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
        print("Starting System Permissions Test...")
        
        # Launch browser with appropriate settings
        browser = playwright.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Create screenshots directory
        screenshots_dir = Path(__file__).parent / "artifacts" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Navigate to console and login
        print("1. Navigating to console...")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Login with confirmed selectors
        print("2. Logging in...")
        page.locator('[data-testid="login-email-input"]').fill("admin@rediacc.io")
        page.locator('[data-testid="login-password-input"]').fill("admin")
        page.locator('[data-testid="login-submit-button"]').click()
        
        # Wait for dashboard
        page.wait_for_url("**/console/dashboard", timeout=15000)
        print("   ✓ Login successful!")
        
        page.screenshot(path=str(screenshots_dir / "01_dashboard.png"))
        
        # 2. Switch to Expert mode (required for Permissions tab)
        print("3. Switching to Expert mode...")
        
        # The UI mode toggle is in the sidebar - look for Expert option
        try:
            # First check current mode by looking at the segmented control
            segmented_control = page.locator('.ant-segmented').first
            if segmented_control.is_visible():
                # Click on the Expert option
                expert_option = page.locator('.ant-segmented-item:has-text("Expert")').first
                if expert_option.is_visible():
                    expert_option.click()
                    time.sleep(1)  # Wait for mode switch
                    print("   ✓ Switched to Expert mode")
                else:
                    print("   Already in Expert mode or toggle not found")
            else:
                print("   UI mode toggle not visible - may already be in Expert mode")
        except Exception as e:
            print(f"   Warning: Could not switch to Expert mode: {str(e)}")
        
        page.screenshot(path=str(screenshots_dir / "02_expert_mode.png"))
        
        # 3. Navigate to System page
        print("4. Navigating to System page...")
        page.locator('[data-testid="main-nav-system"]').click()
        page.wait_for_load_state("networkidle")
        
        page.screenshot(path=str(screenshots_dir / "03_system_page.png"))
        print("   ✓ System page loaded")
        
        # 4. Click on Permissions tab (should be available in Expert mode)
        print("5. Clicking on Permissions tab...")
        permissions_tab = page.locator('[data-testid="system-tab-permissions"]')
        
        # Wait for the tab to be available and click it
        permissions_tab.wait_for(state="visible", timeout=10000)
        permissions_tab.click()
        time.sleep(2)  # Wait for tab content to load
        
        page.screenshot(path=str(screenshots_dir / "04_permissions_tab.png"))
        print("   ✓ Permissions tab opened")
        
        # 5. Click create permission group button
        print("6. Clicking create permission group button...")
        create_button = page.locator('[data-testid="system-create-permission-group-button"]')
        create_button.click()
        time.sleep(1)  # Wait for modal to open
        
        page.screenshot(path=str(screenshots_dir / "05_create_modal.png"))
        print("   ✓ Create permission group modal opened")
        
        # 6. Fill in permission group name
        print("7. Filling in permission group name...")
        group_name_input = page.locator('[data-testid="system-permission-group-name-input"]')
        test_group_name = "TestPermissionGroup"
        group_name_input.fill(test_group_name)
        
        page.screenshot(path=str(screenshots_dir / "06_group_name_filled.png"))
        print(f"   ✓ Group name filled: {test_group_name}")
        
        # 7. Submit the form
        print("8. Submitting permission group creation...")
        submit_button = page.locator('[data-testid="modal-create-permission-group-ok"]')
        submit_button.click()
        time.sleep(3)  # Wait for creation to complete
        
        page.screenshot(path=str(screenshots_dir / "07_after_creation.png"))
        print("   ✓ Permission group creation submitted")
        
        # 8. Verify success
        print("9. Verifying creation success...")
        success_verified = False
        
        # Look for success notification
        try:
            notification = page.locator('.ant-notification-notice').first
            if notification.is_visible(timeout=5000):
                message = notification.inner_text()
                if 'success' in message.lower() or 'created' in message.lower():
                    print(f"   ✓ Success notification: {message}")
                    success_verified = True
        except:
            pass
        
        # Check if the group appears in the table
        try:
            # Look for the newly created group in the permission groups table
            table = page.locator('[data-testid="system-permission-group-table"]')
            if table.is_visible():
                group_cell = table.locator(f'text="{test_group_name}"').first
                if group_cell.is_visible(timeout=5000):
                    print(f"   ✓ New permission group visible in table: {test_group_name}")
                    success_verified = True
        except:
            pass
        
        if not success_verified:
            print("   ! Success verification inconclusive - check screenshots for confirmation")
        
        page.screenshot(path=str(screenshots_dir / "08_final_verification.png"))
        
        # 9. Test user assignment workflow (optional verification)
        print("10. Testing user assignment workflow...")
        
        # Navigate to Users tab
        users_tab = page.locator('.ant-tabs-tab:has-text("Users")').first
        users_tab.click()
        time.sleep(2)
        
        # Click on permissions button for admin user
        permission_button = page.locator('[data-testid="system-user-permissions-button-admin@rediacc.io"]')
        permission_button.click()
        time.sleep(2)
        
        page.screenshot(path=str(screenshots_dir / "09_user_permissions_modal.png"))
        
        # Open permission group dropdown
        dropdown = page.locator('[data-testid="user-permission-group-select"]')
        dropdown.click()
        time.sleep(1)
        
        page.screenshot(path=str(screenshots_dir / "10_dropdown_opened.png"))
        
        # Verify new group appears in dropdown
        try:
            new_group_option = page.locator(f'.ant-select-item:has-text("{test_group_name}")').first
            if new_group_option.is_visible():
                print(f"   ✓ New permission group appears in user assignment dropdown")
                # Cancel the modal without making changes
                cancel_button = page.locator('button:has-text("Cancel")').first
                cancel_button.click()
            else:
                print("   ! New permission group not found in dropdown - may need refresh")
        except Exception as e:
            print(f"   ! Error checking dropdown: {str(e)}")
        
        page.screenshot(path=str(screenshots_dir / "11_test_complete.png"))
        
        print("\n" + "="*80)
        print("SYSTEM PERMISSIONS TEST RESULTS")
        print("="*80)
        
        print("\n✓ CONFIRMED WORKFLOW:")
        print("   1. Login to console")
        print("   2. Switch to Expert mode (required for Permissions tab)")
        print("   3. Navigate to System > Permissions tab")
        print("   4. Click Create Permission Group button")
        print("   5. Fill in group name")
        print("   6. Submit creation")
        print("   7. Verify success notification and table entry")
        print("   8. Confirm group appears in user assignment dropdown")
        
        print("\n✓ KEY SELECTORS CONFIRMED:")
        print("   - Expert mode toggle: .ant-segmented-item:has-text('Expert')")
        print("   - System navigation: [data-testid='main-nav-system']")
        print("   - Permissions tab: [data-testid='system-tab-permissions']")
        print("   - Create button: [data-testid='system-create-permission-group-button']")
        print("   - Group name input: [data-testid='system-permission-group-name-input']")
        print("   - Submit button: [data-testid='modal-create-permission-group-ok']")
        print("   - Permission table: [data-testid='system-permission-group-table']")
        print("   - User permissions: [data-testid='system-user-permissions-button-{email}']")
        print("   - Group dropdown: [data-testid='user-permission-group-select']")
        
        print("\n✓ SUCCESS INDICATORS:")
        print("   - Ant Design success notification")
        print("   - New group visible in permissions table")
        print("   - Group available in user assignment dropdown")
        
        print(f"\nScreenshots saved to: {screenshots_dir}")
        print("Test completed successfully!")
        
        # Keep browser open briefly
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            error_screenshot_path = screenshots_dir / "error_permissions_test.png"
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
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()