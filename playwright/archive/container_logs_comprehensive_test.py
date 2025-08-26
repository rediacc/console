#!/usr/bin/env python3
"""
Comprehensive Container Logs Test with Detailed Observations
"""

import re
import time
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    """Main test execution with comprehensive observations"""
    browser = None
    context = None
    
    try:
        print("Starting Comprehensive Container Logs Test...")
        
        # Create screenshots directory
        screenshots_dir = Path("artifacts/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Launch browser
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Step 1: Navigate to console
        print("\n=== STEP 1: Navigate to Console ===")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # Take screenshot
        page.screenshot(path=str(screenshots_dir / "01_initial_navigation.png"))
        print("Screenshot saved: 01_initial_navigation.png")
        
        # Step 2: Handle login
        print("\n=== STEP 2: Login Process ===")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            print("On login page, proceeding with login...")
        else:
            print("Looking for login link...")
            try:
                login_link = page.get_by_role("banner").get_by_role("link", name="Login")
                with page.expect_popup() as popup_info:
                    login_link.click()
                page = popup_info.value
                print("Navigated to login page via popup")
            except:
                print("No login link found, assuming already on login page")
        
        # Find and fill login form
        print("Filling login credentials...")
        
        # Email input
        email_input = None
        for selector in ['[data-testid="login-email-input"]', 'input[type="email"]', 'input[placeholder*="email" i]']:
            try:
                email_input = page.locator(selector).first
                if email_input.is_visible():
                    break
            except:
                continue
        
        if email_input:
            email_input.fill("admin@rediacc.io")
            print("Email filled successfully")
        else:
            print("ERROR: Could not find email input field")
        
        # Password input
        password_input = None
        for selector in ['[data-testid="login-password-input"]', 'input[type="password"]']:
            try:
                password_input = page.locator(selector).first
                if password_input.is_visible():
                    break
            except:
                continue
        
        if password_input:
            password_input.fill("admin")
            print("Password filled successfully")
        else:
            print("ERROR: Could not find password input field")
        
        # Submit button
        submit_button = None
        for selector in ['[data-testid="login-submit-button"]', 'button[type="submit"]', 'button:has-text("Sign In")']:
            try:
                submit_button = page.locator(selector).first
                if submit_button.is_visible():
                    break
            except:
                continue
        
        if submit_button:
            submit_button.click()
            print("Login button clicked")
        else:
            print("ERROR: Could not find submit button")
        
        # Wait for dashboard
        page.wait_for_url("**/console/dashboard", timeout=10000)
        print("Login successful! Dashboard loaded")
        
        # Take screenshot after login
        page.screenshot(path=str(screenshots_dir / "02_dashboard_after_login.png"))
        print("Screenshot saved: 02_dashboard_after_login.png")
        
        # Step 3: Navigate to Resources
        print("\n=== STEP 3: Navigate to Resources ===")
        resources_link = page.get_by_test_id("main-nav-resources").get_by_text("Resources")
        resources_link.click()
        page.wait_for_load_state("networkidle")
        print("Resources page loaded")
        
        # Take screenshot of resources page
        page.screenshot(path=str(screenshots_dir / "03_resources_page.png"))
        print("Screenshot saved: 03_resources_page.png")
        
        # Step 4: Examine page structure
        print("\n=== STEP 4: Examine Page Structure ===")
        
        # Check for machines table
        machines_table = page.locator('.ant-table-tbody tr')
        machine_count = machines_table.count()
        print(f"Found {machine_count} machines in the table")
        
        # List all machines
        for i in range(machine_count):
            machine_row = machines_table.nth(i)
            machine_text = machine_row.inner_text()
            print(f"  Machine {i+1}: {machine_text[:100]}...")
        
        # Step 5: Look for and expand rediacc11
        print("\n=== STEP 5: Expand Machine rediacc11 ===")
        
        # Try multiple strategies to find rediacc11
        rediacc11_found = False
        
        # Strategy 1: Test ID
        try:
            machine_expand = page.get_by_test_id("machine-expand-rediacc11")
            if machine_expand.is_visible():
                machine_expand.click()
                rediacc11_found = True
                print("Found rediacc11 using test-id strategy")
        except:
            pass
        
        # Strategy 2: Text search
        if not rediacc11_found:
            try:
                machine_row = page.locator('tr:has-text("rediacc11")').first
                if machine_row.is_visible():
                    expand_button = machine_row.locator('button').first
                    expand_button.click()
                    rediacc11_found = True
                    print("Found rediacc11 using text search strategy")
            except:
                pass
        
        if not rediacc11_found:
            print("ERROR: Could not find rediacc11 machine")
            print("Available machines:")
            for i in range(machine_count):
                machine_row = machines_table.nth(i)
                machine_text = machine_row.inner_text()
                print(f"  - {machine_text}")
        else:
            time.sleep(2)  # Wait for expansion animation
            
            # Take screenshot after machine expansion
            page.screenshot(path=str(screenshots_dir / "04_machine_expanded.png"))
            print("Screenshot saved: 04_machine_expanded.png")
        
        # Step 6: Look for repositories
        print("\n=== STEP 6: Look for Repositories ===")
        
        # Check if repositories are visible after expansion
        try:
            repo_table = page.get_by_test_id("machine-repo-list-table")
            if repo_table.is_visible():
                print("Repository table is visible")
                
                # Get all repository rows
                repo_rows = repo_table.locator('tbody tr')
                repo_count = repo_rows.count()
                print(f"Found {repo_count} repositories")
                
                # List all repositories
                for i in range(repo_count):
                    repo_row = repo_rows.nth(i)
                    repo_text = repo_row.inner_text()
                    print(f"  Repository {i+1}: {repo_text[:100]}...")
                
                # Try to expand first repository
                if repo_count > 0:
                    first_repo_row = repo_rows.first
                    expand_buttons = first_repo_row.locator('button.ant-table-row-expand-icon')
                    if expand_buttons.count() > 0:
                        expand_buttons.first.click()
                        print("Expanded first repository")
                        time.sleep(2)
                        
                        # Take screenshot after repository expansion
                        page.screenshot(path=str(screenshots_dir / "05_repository_expanded.png"))
                        print("Screenshot saved: 05_repository_expanded.png")
            else:
                print("Repository table is not visible")
        except Exception as e:
            print(f"Error accessing repository table: {e}")
        
        # Step 7: Look for container actions
        print("\n=== STEP 7: Look for Container Actions ===")
        
        # Check for any container-related elements
        container_elements = page.locator('*[data-testid*="container"]')
        container_count = container_elements.count()
        print(f"Found {container_count} container-related elements")
        
        for i in range(container_count):
            element = container_elements.nth(i)
            test_id = element.get_attribute('data-testid')
            print(f"  Container element {i+1}: {test_id}")
        
        # Look for specific container actions buttons
        container_action_selectors = [
            'button[data-testid*="container-actions"]',
            'button[data-testid*="machine-repo-list-container-actions"]',
            'button:has-text("Actions")',
            '.ant-table-row button[title*="container"]'
        ]
        
        container_actions_found = False
        for selector in container_action_selectors:
            try:
                elements = page.locator(selector)
                count = elements.count()
                if count > 0:
                    print(f"Found {count} elements matching: {selector}")
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            print(f"  Visible element {i+1}")
                            container_actions_found = True
                            
                            # Click the first visible container actions button
                            element.click()
                            print("Clicked container actions button")
                            time.sleep(1)
                            
                            # Take screenshot after clicking
                            page.screenshot(path=str(screenshots_dir / "06_container_actions_menu.png"))
                            print("Screenshot saved: 06_container_actions_menu.png")
                            
                            # Look for container_logs option
                            logs_option = page.get_by_text("container_logs")
                            if logs_option.is_visible():
                                print("Found container_logs option")
                                logs_option.click()
                                print("Clicked container_logs!")
                                time.sleep(3)
                                
                                # Take screenshot after clicking logs
                                page.screenshot(path=str(screenshots_dir / "07_container_logs_displayed.png"))
                                print("Screenshot saved: 07_container_logs_displayed.png")
                                
                                # Check for log display elements
                                print("\n=== STEP 8: Examine Log Display ===")
                                
                                # Look for various log display patterns
                                log_selectors = [
                                    '.ant-modal',  # Modal dialog
                                    '.ant-drawer',  # Drawer panel
                                    'pre',  # Preformatted text
                                    'code',  # Code blocks
                                    '*[class*="log"]',  # Elements with "log" in class
                                    '*[class*="console"]',  # Elements with "console" in class
                                    'textarea'  # Text areas
                                ]
                                
                                for selector in log_selectors:
                                    elements = page.locator(selector)
                                    count = elements.count()
                                    if count > 0:
                                        print(f"Found {count} log-related elements: {selector}")
                                        for i in range(count):
                                            element = elements.nth(i)
                                            if element.is_visible():
                                                text_content = element.inner_text()[:200]
                                                print(f"  Content preview: {text_content}...")
                                
                                # Check for success messages
                                success_messages = page.locator('*:has-text("success"), *:has-text("Success"), .ant-message-success')
                                if success_messages.count() > 0:
                                    print("Found success messages:")
                                    for i in range(success_messages.count()):
                                        msg = success_messages.nth(i)
                                        if msg.is_visible():
                                            print(f"  Success: {msg.inner_text()}")
                                
                                # Check console messages
                                print("\n=== Console Messages ===")
                                page.wait_for_timeout(1000)  # Wait a bit for any async operations
                                
                                # Get console logs (if any)
                                # Note: Console logs are captured during page creation, not retroactively
                                
                            else:
                                print("container_logs option not found in menu")
                                
                                # List all available menu options
                                menu_items = page.locator('.ant-dropdown-menu-item, .ant-menu-item')
                                menu_count = menu_items.count()
                                print(f"Available menu items ({menu_count}):")
                                for i in range(menu_count):
                                    item = menu_items.nth(i)
                                    if item.is_visible():
                                        print(f"  - {item.inner_text()}")
                            
                            break  # Exit after first successful click
            except Exception as e:
                print(f"Error with selector {selector}: {e}")
        
        if not container_actions_found:
            print("No container actions buttons found")
            print("This might indicate:")
            print("  - No containers are currently running")
            print("  - The repository is not active")
            print("  - Different UI state than expected")
        
        # Final screenshot
        page.screenshot(path=str(screenshots_dir / "08_final_state.png"))
        print("Screenshot saved: 08_final_state.png")
        
        print("\n=== TEST COMPLETED ===")
        print("Check the screenshots in artifacts/screenshots/ for visual confirmation")
        
        # Keep browser open for manual inspection
        print("Keeping browser open for 10 seconds for manual inspection...")
        time.sleep(10)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            error_screenshot = screenshots_dir / "error_screenshot.png"
            page.screenshot(path=str(error_screenshot))
            print(f"Error screenshot saved to: {error_screenshot}")
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