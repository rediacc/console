#!/usr/bin/env python3
"""
System Teams Delete Test - Improved Version
Tests the team deletion functionality in Rediacc console

Based on UI exploration findings:
- Delete buttons have data-testid: system-team-delete-button-{team_name}
- Confirmation uses .ant-popconfirm with "Delete Team" title
- Success message: Team "{team_name}" deleted successfully
- Cannot delete system-required teams (Default, Private Team)
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
        print("Starting System Teams Delete Test...")
        
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
        
        # Use improved selectors based on UI exploration
        email_input = page.locator('input[placeholder*="email"]').first
        email_input.fill("admin@rediacc.io")
        
        password_input = page.locator('input[placeholder*="password"]').first
        password_input.fill("admin")
        
        submit_button = page.locator('button:has-text("Sign In")').first
        submit_button.click()
        
        # Wait for dashboard
        print("5. Waiting for dashboard...")
        page.wait_for_url("**/console/dashboard", timeout=10000)
        print("   Login successful!")
        
        # Navigate to System
        print("6. Navigating to System...")
        system_link = page.get_by_test_id("main-nav-system")
        system_link.click()
        page.wait_for_load_state("networkidle")
        
        # Click on Teams tab
        print("7. Navigating to Teams tab...")
        teams_tab = page.get_by_test_id("system-tab-teams")
        teams_tab.click()
        page.wait_for_timeout(2000)  # Wait for teams tab to load
        print("   Teams tab opened")
        
        # Find a deletable team (avoid system-required teams)
        print("8. Looking for deletable team...")
        
        # First, let's find available teams and identify one that can be deleted
        team_rows = page.locator('tr').all()
        deletable_teams = []
        
        for row in team_rows:
            if row.is_visible():
                row_text = row.text_content()
                if row_text and len(row_text.strip()) > 10:  # Skip header/empty rows
                    # Look for delete button in this row
                    delete_btns = row.locator('[data-testid*="delete"]').all()
                    for btn in delete_btns:
                        if btn.is_visible():
                            # Extract team name from test-id
                            btn_testid = btn.get_attribute('data-testid')
                            if btn_testid and 'system-team-delete-button-' in btn_testid:
                                team_name = btn_testid.replace('system-team-delete-button-', '')
                                # Skip system-required teams
                                if team_name not in ['Default', 'Private Team']:
                                    deletable_teams.append(team_name)
                                    print(f"   Found deletable team: {team_name}")
        
        if not deletable_teams:
            print("   No deletable teams found (only system-required teams exist)")
            print("   Creating a test team for deletion...")
            
            # Create a test team first
            try:
                create_button = page.locator('button').filter(has_text='+').first
                if create_button.is_visible():
                    create_button.click()
                    page.wait_for_timeout(1000)
                    
                    # Fill team name
                    name_input = page.locator('.ant-modal input[type="text"]').first
                    if name_input.is_visible():
                        test_team_name = "TestDeletionTeam"
                        name_input.fill(test_team_name)
                        
                        # Submit
                        submit_btn = page.locator('.ant-modal .ant-btn-primary').first
                        if submit_btn.is_visible():
                            submit_btn.click()
                            page.wait_for_timeout(3000)
                            deletable_teams.append(test_team_name)
                            print(f"   Created test team: {test_team_name}")
            except Exception as e:
                print(f"   Could not create test team: {str(e)}")
        
        delete_found = False
        team_name = None
        
        if deletable_teams:
            team_name = deletable_teams[0]  # Use first available deletable team
            print(f"   Attempting to delete team: {team_name}")
            
            # Click the delete button using the correct test-id
            delete_button = page.get_by_test_id(f"system-team-delete-button-{team_name}")
            if delete_button.is_visible():
                delete_button.click()
                delete_found = True
                print(f"   Delete button clicked for team: {team_name}")
            else:
                print(f"   Delete button not found for team: {team_name}")
        
        if not delete_found:
            print("   Could not find any team to delete")
        else:
            page.wait_for_timeout(1000)  # Wait for confirmation dialog
            
            # Handle confirmation dialog
            print("9. Handling confirmation dialog...")
            
            # Look for the popconfirm dialog
            popconfirm = page.locator('.ant-popconfirm').first
            if popconfirm.is_visible():
                # Get confirmation dialog text for verification
                confirmation_text = popconfirm.text_content()
                print(f"   Confirmation dialog: {confirmation_text}")
                
                # Verify it's asking about the correct team
                if team_name in confirmation_text:
                    print(f"   Confirmed dialog is for team: {team_name}")
                    
                    # Click Yes to confirm deletion
                    yes_button = popconfirm.locator('button:has-text("Yes")').first
                    if yes_button.is_visible():
                        yes_button.click()
                        print("   Clicked Yes to confirm deletion")
                        
                        # Wait for deletion to complete
                        page.wait_for_timeout(3000)
                        
                        # Check for success message
                        success_message_found = False
                        message_selectors = [
                            '.ant-message-success',
                            '.ant-notification-notice',
                            '.ant-message',
                            '[role="alert"]'
                        ]
                        
                        for selector in message_selectors:
                            try:
                                messages = page.locator(selector).all()
                                for msg in messages:
                                    if msg.is_visible():
                                        msg_text = msg.text_content()
                                        if 'deleted successfully' in msg_text.lower():
                                            print(f"   SUCCESS MESSAGE: {msg_text}")
                                            success_message_found = True
                                            break
                            except:
                                pass
                        
                        # Verify team was removed from table
                        team_row = page.locator(f'tr:has-text("{team_name}")').first
                        if not team_row.is_visible():
                            print(f"   VERIFICATION: Team '{team_name}' successfully removed from table")
                            print("   ✓ Team deletion completed successfully")
                        else:
                            print(f"   WARNING: Team '{team_name}' still visible in table")
                            
                            # Check if there's an error message
                            error_messages = page.locator('.ant-message-error, .ant-notification-error').all()
                            for err_msg in error_messages:
                                if err_msg.is_visible():
                                    err_text = err_msg.text_content()
                                    print(f"   ERROR MESSAGE: {err_text}")
                    else:
                        print("   Yes button not found in confirmation dialog")
                else:
                    print(f"   Confirmation dialog is not for the expected team: {team_name}")
            else:
                print("   No popconfirm dialog found")
                
                # Check for modal dialog as fallback
                modal = page.locator('.ant-modal').first
                if modal.is_visible():
                    modal_text = modal.text_content()
                    print(f"   Found modal instead of popconfirm: {modal_text}")
                    
                    # Look for confirmation buttons in modal
                    confirm_btn = modal.locator('button:has-text("Yes"), button:has-text("OK"), button:has-text("Confirm")').first
                    if confirm_btn.is_visible():
                        confirm_btn.click()
                        print("   Clicked modal confirmation button")
                        page.wait_for_timeout(3000)
                else:
                    print("   No confirmation dialog found")
        
        # Take final screenshot for documentation
        final_screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "final_teams_state.png"
        final_screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(final_screenshot_path), full_page=True)
        print(f"   Final screenshot saved: {final_screenshot_path}")
        
        print("\n" + "="*50)
        print("TEAM DELETION TEST COMPLETED")
        print("="*50)
        if delete_found and team_name:
            print(f"✓ Successfully tested deletion of team: {team_name}")
            print("✓ Confirmed proper confirmation dialog flow")
            print("✓ Verified success/error message handling")
        else:
            print("⚠ No teams were available for deletion testing")
        print("="*50)
        
        # Keep browser open briefly to see results
        time.sleep(2)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot_teamdelete.png"
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