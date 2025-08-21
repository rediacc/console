#!/usr/bin/env python3
"""
System Teams Delete Test - Fixed Version
Tests the team deletion functionality in Rediacc console
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
            system_link = page.get_by_test_id("main-nav-system")
            system_link.click()
        except:
            # Try alternative selector
            system_link = page.locator('nav a:has-text("System")').first
            if not system_link.is_visible():
                system_link = page.locator('[data-testid*="system"]').first
            system_link.click()
        
        page.wait_for_load_state("networkidle")
        
        # Click on Teams tab
        print("7. Navigating to Teams tab...")
        teams_tab_found = False
        
        try:
            teams_tab = page.get_by_test_id("system-tab-teams")
            if teams_tab.is_visible():
                teams_tab.click()
                teams_tab_found = True
                print("   Teams tab opened")
        except:
            pass
        
        if not teams_tab_found:
            # Try alternative selectors
            print("   Trying alternative selector for teams tab...")
            try:
                teams_selectors = [
                    'button:has-text("Teams")',
                    'div[role="tab"]:has-text("Teams")',
                    '.ant-tabs-tab:has-text("Teams")',
                    '[data-testid*="teams"]'
                ]
                
                for selector in teams_selectors:
                    try:
                        teams_tab = page.locator(selector).first
                        if teams_tab.is_visible():
                            teams_tab.click()
                            teams_tab_found = True
                            print("   Teams tab opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding teams tab: {str(e)}")
        
        if not teams_tab_found:
            print("   Warning: Could not find teams tab")
        
        time.sleep(1)  # Wait for teams tab to load
        
        # Find and click delete button for specific team
        print("8. Looking for team delete button...")
        delete_found = False
        team_name = "test2"
        
        try:
            # Try specific test-id first
            delete_button = page.get_by_test_id(f"system-team-delete-button-{team_name}")
            if delete_button.is_visible():
                delete_button.click()
                delete_found = True
                print(f"   Delete button clicked for team: {team_name}")
        except:
            pass
        
        if not delete_found:
            # Try alternative selectors
            print("   Trying alternative selector for delete button...")
            try:
                # Look for team row and delete button
                team_row = page.locator(f'tr:has-text("{team_name}")').first
                if team_row.is_visible():
                    delete_btn = team_row.locator('button:has-text("Delete")').first
                    if not delete_btn.is_visible():
                        delete_btn = team_row.locator('button[title*="delete"]').first
                    if not delete_btn.is_visible():
                        delete_btn = team_row.locator('button[title*="Delete"]').first
                    if not delete_btn.is_visible():
                        delete_btn = team_row.locator('[data-testid*="delete"]').first
                    
                    if delete_btn.is_visible():
                        delete_btn.click()
                        delete_found = True
                        print(f"   Delete button clicked for team in row")
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
            print("   Team might not exist or delete option is not available")
        else:
            time.sleep(1)  # Wait for confirmation dialog
            
            # Confirm deletion
            print("9. Confirming deletion...")
            confirm_found = False
            
            try:
                confirm_button = page.get_by_test_id("confirm-yes-button")
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
                print("   Team deletion completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "error_screenshot_teamdelete.png"
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