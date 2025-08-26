#!/usr/bin/env python3
"""
Container Logs Test with Machine Setup
This test first ensures we have a machine and repository before testing container logs
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
        print("Starting Container Logs Test with Setup...")
        
        # Create screenshots directory
        screenshots_dir = Path("artifacts/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Launch browser
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Step 1: Login
        print("\n=== STEP 1: Login ===")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Handle login
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            print("On login page, proceeding with login...")
            
            # Fill login form
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
                
            # Wait for dashboard
            page.wait_for_url("**/console/dashboard", timeout=10000)
            print("Login successful!")
        
        # Step 2: Navigate to Resources and wait for loading
        print("\n=== STEP 2: Navigate to Resources ===")
        resources_link = page.get_by_test_id("main-nav-resources").get_by_text("Resources")
        resources_link.click()
        
        # Wait longer for the resources to load
        print("Waiting for resources to load...")
        page.wait_for_load_state("networkidle")
        time.sleep(5)  # Additional wait for data loading
        
        # Take screenshot after waiting
        page.screenshot(path=str(screenshots_dir / "01_resources_after_wait.png"))
        print("Screenshot saved: 01_resources_after_wait.png")
        
        # Step 3: Check current machines
        print("\n=== STEP 3: Check Available Machines ===")
        
        # Look for the machines table more thoroughly
        try:
            # Wait for table to be visible
            page.wait_for_selector('.ant-table-tbody', timeout=10000)
            
            # Check if we have any machines
            machine_rows = page.locator('.ant-table-tbody tr')
            machine_count = machine_rows.count()
            print(f"Found {machine_count} machine rows")
            
            if machine_count == 0:
                print("No machines found in table")
            else:
                for i in range(machine_count):
                    row = machine_rows.nth(i)
                    row_text = row.inner_text()
                    print(f"  Machine row {i+1}: {row_text}")
                    
                    # Check if this row contains actual data or "No data"
                    if "No data" not in row_text and row_text.strip():
                        print(f"    Found valid machine data: {row_text}")
                        
                        # Try to expand this machine
                        try:
                            expand_button = row.locator('button').first
                            if expand_button.is_visible():
                                print(f"    Expanding machine row {i+1}")
                                expand_button.click()
                                time.sleep(2)
                                
                                # Take screenshot after expansion
                                page.screenshot(path=str(screenshots_dir / f"02_machine_{i+1}_expanded.png"))
                                print(f"Screenshot saved: 02_machine_{i+1}_expanded.png")
                                
                                # Look for repositories in this expanded machine
                                repo_table = page.get_by_test_id("machine-repo-list-table")
                                if repo_table.is_visible():
                                    print("    Repository table visible")
                                    
                                    # Get repository rows
                                    repo_rows = repo_table.locator('tbody tr')
                                    repo_count = repo_rows.count()
                                    print(f"    Found {repo_count} repositories")
                                    
                                    for j in range(repo_count):
                                        repo_row = repo_rows.nth(j)
                                        repo_text = repo_row.inner_text()
                                        print(f"      Repository {j+1}: {repo_text}")
                                        
                                        # Try to expand repository
                                        repo_expand_button = repo_row.locator('button.ant-table-row-expand-icon').first
                                        if repo_expand_button.is_visible():
                                            print(f"      Expanding repository {j+1}")
                                            repo_expand_button.click()
                                            time.sleep(2)
                                            
                                            # Take screenshot after repo expansion
                                            page.screenshot(path=str(screenshots_dir / f"03_repo_{j+1}_expanded.png"))
                                            print(f"Screenshot saved: 03_repo_{j+1}_expanded.png")
                                            
                                            # Now look for container actions
                                            print("      Looking for container actions...")
                                            
                                            # Multiple strategies to find container actions
                                            container_selectors = [
                                                'button[data-testid*="container-actions"]',
                                                'button[data-testid*="machine-repo-list-container-actions"]',
                                                'button:has-text("Actions")',
                                                'button[title*="Container"]',
                                                'button[title*="Actions"]'
                                            ]
                                            
                                            container_found = False
                                            for selector in container_selectors:
                                                try:
                                                    elements = page.locator(selector)
                                                    count = elements.count()
                                                    if count > 0:
                                                        print(f"        Found {count} elements with selector: {selector}")
                                                        for k in range(count):
                                                            element = elements.nth(k)
                                                            if element.is_visible():
                                                                print(f"        Clicking container actions button")
                                                                element.click()
                                                                time.sleep(1)
                                                                container_found = True
                                                                
                                                                # Take screenshot of menu
                                                                page.screenshot(path=str(screenshots_dir / "04_container_actions_menu.png"))
                                                                print("Screenshot saved: 04_container_actions_menu.png")
                                                                
                                                                # Look for container_logs option
                                                                logs_option = page.get_by_text("container_logs")
                                                                if logs_option.is_visible():
                                                                    print("        Found container_logs option!")
                                                                    logs_option.click()
                                                                    print("        Clicked container_logs!")
                                                                    
                                                                    # Wait for logs to load
                                                                    time.sleep(3)
                                                                    
                                                                    # Take screenshot of logs
                                                                    page.screenshot(path=str(screenshots_dir / "05_container_logs_display.png"))
                                                                    print("Screenshot saved: 05_container_logs_display.png")
                                                                    
                                                                    # Examine what's displayed
                                                                    print("\n=== STEP 4: Examine Log Display ===")
                                                                    
                                                                    # Check for modal or drawer
                                                                    modal = page.locator('.ant-modal')
                                                                    if modal.is_visible():
                                                                        print("        Logs displayed in modal")
                                                                        modal_content = modal.inner_text()
                                                                        print(f"        Modal content: {modal_content[:200]}...")
                                                                    
                                                                    drawer = page.locator('.ant-drawer')
                                                                    if drawer.is_visible():
                                                                        print("        Logs displayed in drawer")
                                                                        drawer_content = drawer.inner_text()
                                                                        print(f"        Drawer content: {drawer_content[:200]}...")
                                                                    
                                                                    # Check for preformatted text
                                                                    pre_elements = page.locator('pre')
                                                                    if pre_elements.count() > 0:
                                                                        print(f"        Found {pre_elements.count()} <pre> elements")
                                                                        for l in range(pre_elements.count()):
                                                                            pre = pre_elements.nth(l)
                                                                            if pre.is_visible():
                                                                                content = pre.inner_text()
                                                                                print(f"        Pre content: {content[:200]}...")
                                                                    
                                                                    # Check for code elements
                                                                    code_elements = page.locator('code')
                                                                    if code_elements.count() > 0:
                                                                        print(f"        Found {code_elements.count()} <code> elements")
                                                                    
                                                                    # Check for success messages
                                                                    success_elements = page.locator('.ant-message-success, *:has-text("Success"), *:has-text("success")')
                                                                    if success_elements.count() > 0:
                                                                        print("        Found success messages:")
                                                                        for m in range(success_elements.count()):
                                                                            msg = success_elements.nth(m)
                                                                            if msg.is_visible():
                                                                                print(f"        - {msg.inner_text()}")
                                                                    
                                                                    # Final comprehensive screenshot
                                                                    page.screenshot(path=str(screenshots_dir / "06_final_logs_state.png"))
                                                                    print("Screenshot saved: 06_final_logs_state.png")
                                                                    
                                                                    print("\n=== Container Logs Test Successful! ===")
                                                                    
                                                                else:
                                                                    print("        container_logs option not found")
                                                                    # List available menu options
                                                                    menu_items = page.locator('.ant-dropdown-menu-item, .ant-menu-item')
                                                                    if menu_items.count() > 0:
                                                                        print("        Available menu options:")
                                                                        for l in range(menu_items.count()):
                                                                            item = menu_items.nth(l)
                                                                            if item.is_visible():
                                                                                print(f"        - {item.inner_text()}")
                                                                
                                                                break
                                                except Exception as e:
                                                    print(f"        Error with selector {selector}: {e}")
                                            
                                            if not container_found:
                                                print("      No container actions found for this repository")
                                            
                                            break  # Only test first repository for now
                                else:
                                    print("    No repository table visible")
                                
                                break  # Only test first machine for now
                        except Exception as e:
                            print(f"    Error expanding machine: {e}")
        
        except Exception as e:
            print(f"Error checking machines: {e}")
        
        # If no machines found, show current page state
        if machine_count == 0 or all("No data" in row.inner_text() for row in [machine_rows.nth(i) for i in range(machine_count)]):
            print("\n=== No Valid Machines Found ===")
            print("Current page may be showing empty state or still loading")
            
            # Take final screenshot showing current state
            page.screenshot(path=str(screenshots_dir / "07_no_machines_state.png"))
            print("Screenshot saved: 07_no_machines_state.png")
        
        print("\n=== Test Completed ===")
        print("Check screenshots in artifacts/screenshots/ for visual confirmation")
        
        # Keep browser open for inspection
        time.sleep(10)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            error_screenshot = screenshots_dir / "error_screenshot.png"
            page.screenshot(path=str(error_screenshot))
            print(f"Error screenshot saved to: {error_screenshot}")
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
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()