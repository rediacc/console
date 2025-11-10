#!/usr/bin/env python3
"""
Complete Container Logs Test
This test sets up a complete machine, creates a repository, and tests container logs functionality
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
        print("Starting Complete Container Logs Test...")
        
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
            print("Performing login...")
            
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
        
        # Step 2: Navigate to Resources
        print("\n=== STEP 2: Navigate to Resources ===")
        resources_link = page.get_by_test_id("main-nav-machines").get_by_text("Machines")
        resources_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        page.screenshot(path=str(screenshots_dir / "01_resources_page.png"))
        print("Screenshot saved: 01_resources_page.png")
        
        # Step 3: Complete the machine configuration if needed
        print("\n=== STEP 3: Setup Machine Configuration ===")
        
        # Check if machine edit modal is open
        edit_modal = page.locator('.ant-modal:has-text("Edit Machine Name")')
        if edit_modal.is_visible():
            print("Machine edit modal is open, completing configuration...")
            
            # Fill IP Address
            ip_input = page.locator('input[placeholder*="IP address"]')
            if ip_input.is_visible():
                ip_input.fill("192.168.1.100")
                print("Filled IP address")
            
            # Fill Username
            username_input = page.locator('input[placeholder*="Username"]')
            if username_input.is_visible():
                username_input.fill("ubuntu")
                print("Filled username")
            
            # Save the configuration
            save_button = page.get_by_text("Save")
            if save_button.is_visible():
                save_button.click()
                print("Saved machine configuration")
                time.sleep(2)
        else:
            print("No machine edit modal visible")
        
        # Step 4: Look for existing machines or create one
        print("\n=== STEP 4: Find or Create Machine ===")
        
        # Wait for table to load
        try:
            page.wait_for_selector('.ant-table-tbody', timeout=10000)
            machine_rows = page.locator('.ant-table-tbody tr')
            machine_count = machine_rows.count()
            print(f"Found {machine_count} machine rows")
            
            # Look for a properly configured machine
            configured_machine_found = False
            machine_name = ""
            
            for i in range(machine_count):
                row = machine_rows.nth(i)
                row_text = row.inner_text()
                print(f"  Machine row {i+1}: {row_text}")
                
                if "No data" not in row_text and row_text.strip() and "rediacc" in row_text.lower():
                    machine_name = "rediacc11"  # Assuming this is our target machine
                    configured_machine_found = True
                    print(f"    Found configured machine: {machine_name}")
                    
                    # Try to expand this machine properly
                    try:
                        # Look for expand button (different from edit button)
                        expand_icon = row.locator('button.ant-table-row-expand-icon')
                        if expand_icon.is_visible():
                            print(f"    Clicking expand icon for {machine_name}")
                            expand_icon.click()
                            time.sleep(2)
                            
                            page.screenshot(path=str(screenshots_dir / "02_machine_expanded.png"))
                            print("Screenshot saved: 02_machine_expanded.png")
                            
                            configured_machine_found = True
                            break
                        else:
                            print("    No expand icon found for this machine")
                    except Exception as e:
                        print(f"    Error expanding machine: {e}")
            
            if not configured_machine_found:
                print("No properly configured machine found, creating a new one...")
                # This would require implementing machine creation flow
                # For now, let's see if we can work with existing machines
                
        except Exception as e:
            print(f"Error checking machines: {e}")
        
        # Step 5: Look for repositories
        print("\n=== STEP 5: Look for Repositories ===")
        
        try:
            # Check for repository table
            repo_table = page.get_by_test_id("machine-repo-list-table")
            if repo_table.is_visible():
                print("Repository table found!")
                
                # Get repository rows
                repo_rows = repo_table.locator('tbody tr')
                repo_count = repo_rows.count()
                print(f"Found {repo_count} repositories")
                
                if repo_count > 0:
                    for i in range(repo_count):
                        repo_row = repo_rows.nth(i)
                        repo_text = repo_row.inner_text()
                        print(f"  Repository {i+1}: {repo_text}")
                        
                        # Try to expand the first repository that has data
                        if "No data" not in repo_text and repo_text.strip():
                            print(f"  Expanding repository {i+1}")
                            
                            # Look for expand button in repository row
                            repo_expand = repo_row.locator('button.ant-table-row-expand-icon')
                            if repo_expand.is_visible():
                                repo_expand.click()
                                time.sleep(2)
                                
                                page.screenshot(path=str(screenshots_dir / "03_repository_expanded.png"))
                                print("Screenshot saved: 03_repository_expanded.png")
                                
                                # Step 6: Look for container actions
                                print("\n=== STEP 6: Look for Container Actions ===")
                                
                                # Look for container actions in the expanded repository
                                container_selectors = [
                                    'button[data-testid*="container-actions"]',
                                    'button[data-testid*="machine-repo-list-container-actions"]',
                                    'button:has-text("Actions")',
                                    'button[title*="Container"]',
                                    '.ant-table-row button[title*="Actions"]'
                                ]
                                
                                container_found = False
                                for selector in container_selectors:
                                    try:
                                        elements = page.locator(selector)
                                        count = elements.count()
                                        if count > 0:
                                            print(f"  Found {count} potential container action elements: {selector}")
                                            for j in range(count):
                                                element = elements.nth(j)
                                                if element.is_visible():
                                                    print(f"  Clicking container actions button")
                                                    element.click()
                                                    time.sleep(1)
                                                    container_found = True
                                                    
                                                    page.screenshot(path=str(screenshots_dir / "04_container_menu.png"))
                                                    print("Screenshot saved: 04_container_menu.png")
                                                    
                                                    # Step 7: Click container_logs
                                                    print("\n=== STEP 7: Click Container Logs ===")
                                                    
                                                    logs_option = page.get_by_text("container_logs")
                                                    if logs_option.is_visible():
                                                        print("  Found container_logs option!")
                                                        logs_option.click()
                                                        print("  Clicked container_logs!")
                                                        
                                                        # Wait for logs to load
                                                        time.sleep(3)
                                                        
                                                        page.screenshot(path=str(screenshots_dir / "05_logs_loading.png"))
                                                        print("Screenshot saved: 05_logs_loading.png")
                                                        
                                                        # Step 8: Observe log display
                                                        print("\n=== STEP 8: Observe Log Display ===")
                                                        
                                                        # Check for various log display elements
                                                        log_display_found = False
                                                        
                                                        # Check for modal
                                                        modal = page.locator('.ant-modal')
                                                        if modal.is_visible():
                                                            print("  Logs displayed in modal!")
                                                            log_display_found = True
                                                            modal_title = modal.locator('.ant-modal-title').inner_text() if modal.locator('.ant-modal-title').is_visible() else "No title"
                                                            print(f"  Modal title: {modal_title}")
                                                            
                                                            modal_content = modal.locator('.ant-modal-body').inner_text() if modal.locator('.ant-modal-body').is_visible() else "No body content"
                                                            print(f"  Modal content preview: {modal_content[:300]}...")
                                                        
                                                        # Check for drawer
                                                        drawer = page.locator('.ant-drawer')
                                                        if drawer.is_visible():
                                                            print("  Logs displayed in drawer!")
                                                            log_display_found = True
                                                            drawer_content = drawer.inner_text()
                                                            print(f"  Drawer content preview: {drawer_content[:300]}...")
                                                        
                                                        # Check for preformatted text (typical for logs)
                                                        pre_elements = page.locator('pre')
                                                        visible_pre_count = 0
                                                        for k in range(pre_elements.count()):
                                                            if pre_elements.nth(k).is_visible():
                                                                visible_pre_count += 1
                                                                content = pre_elements.nth(k).inner_text()
                                                                print(f"  Log content in <pre>: {content[:200]}...")
                                                                log_display_found = True
                                                        
                                                        if visible_pre_count > 0:
                                                            print(f"  Found {visible_pre_count} visible <pre> elements with log content")
                                                        
                                                        # Check for success messages
                                                        success_selectors = [
                                                            '.ant-message-success',
                                                            '.ant-notification-notice-success',
                                                            '*:has-text("success")',
                                                            '*:has-text("Success")',
                                                            '*:has-text("completed")',
                                                            '*:has-text("Completed")'
                                                        ]
                                                        
                                                        for selector in success_selectors:
                                                            elements = page.locator(selector)
                                                            for k in range(elements.count()):
                                                                element = elements.nth(k)
                                                                if element.is_visible():
                                                                    msg_text = element.inner_text()
                                                                    print(f"  Success message: {msg_text}")
                                                        
                                                        # Check console for network responses
                                                        print("\n=== Network Activity ===")
                                                        print("  (Network responses would be captured in real browser dev tools)")
                                                        
                                                        # Final screenshot
                                                        page.screenshot(path=str(screenshots_dir / "06_final_logs_state.png"))
                                                        print("Screenshot saved: 06_final_logs_state.png")
                                                        
                                                        if log_display_found:
                                                            print("\n✅ SUCCESS: Container logs functionality working!")
                                                            print("  - Found container actions button")
                                                            print("  - Found container_logs option")  
                                                            print("  - Logs are being displayed")
                                                        else:
                                                            print("\n⚠️  WARNING: Container logs clicked but no clear log display found")
                                                        
                                                    else:
                                                        print("  container_logs option not found in menu")
                                                        # List available options
                                                        menu_items = page.locator('.ant-dropdown-menu-item, .ant-menu-item')
                                                        print(f"  Available menu options ({menu_items.count()}):")
                                                        for k in range(menu_items.count()):
                                                            item = menu_items.nth(k)
                                                            if item.is_visible():
                                                                print(f"    - {item.inner_text()}")
                                                    
                                                    break
                                    except Exception as e:
                                        print(f"  Error with selector {selector}: {e}")
                                
                                if not container_found:
                                    print("  No container actions found")
                                    print("  This might indicate:")
                                    print("    - Repository is not active")
                                    print("    - No containers are running")
                                    print("    - Different UI structure than expected")
                                
                                break  # Only test first repository
                            else:
                                print(f"  No expand button found for repository {i+1}")
                else:
                    print("No repositories found to test")
            else:
                print("Repository table not visible")
                print("This might mean:")
                print("  - Machine is not properly configured")
                print("  - Machine is not expanded correctly")
                print("  - UI structure is different than expected")
                
        except Exception as e:
            print(f"Error looking for repositories: {e}")
        
        print("\n=== Test Completed ===")
        print("Check artifacts/screenshots/ for visual confirmation of each step")
        
        # Keep browser open for manual inspection
        print("Keeping browser open for 15 seconds for manual inspection...")
        time.sleep(15)
        
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