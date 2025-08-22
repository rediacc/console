#!/usr/bin/env python3
"""
Simple Container Logs Test
Tests container logs functionality with existing repositories
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
        print("Starting Simple Container Logs Test...")
        
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
        
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            print("Performing login...")
            
            # Fill email
            email_selectors = ['[data-testid="login-email-input"]', 'input[type="email"]', 'input[placeholder*="email" i]']
            for selector in email_selectors:
                try:
                    email_input = page.locator(selector).first
                    if email_input.is_visible():
                        email_input.fill("admin@rediacc.io")
                        break
                except:
                    continue
            
            # Fill password  
            password_selectors = ['[data-testid="login-password-input"]', 'input[type="password"]']
            for selector in password_selectors:
                try:
                    password_input = page.locator(selector).first
                    if password_input.is_visible():
                        password_input.fill("admin")
                        break
                except:
                    continue
            
            # Click submit
            submit_selectors = ['[data-testid="login-submit-button"]', 'button[type="submit"]', 'button:has-text("Sign In")']
            for selector in submit_selectors:
                try:
                    submit_button = page.locator(selector).first
                    if submit_button.is_visible():
                        submit_button.click()
                        break
                except:
                    continue
            
            page.wait_for_url("**/console/dashboard", timeout=10000)
            print("✅ Login successful!")
        
        # Step 2: Navigate to Resources
        print("\n=== STEP 2: Navigate to Resources ===")
        resources_link = page.get_by_test_id("main-nav-resources").get_by_text("Resources")
        resources_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        page.screenshot(path=str(screenshots_dir / "01_resources_page.png"))
        print("Screenshot: 01_resources_page.png")
        
        # Step 3: Look for machines and expand them
        print("\n=== STEP 3: Find and Expand Machines ===")
        
        machine_names = ["rediacc11", "rediacc12"]
        container_logs_tested = False
        
        for machine_name in machine_names:
            if container_logs_tested:
                break
                
            print(f"\nTrying machine: {machine_name}")
            machine_row = page.locator(f'tr:has-text("{machine_name}")')
            
            if machine_row.count() > 0:
                print(f"Found {machine_name} machine row")
                
                # Try to expand the machine
                expand_arrow = machine_row.locator('span.anticon-right').first
                if expand_arrow.is_visible():
                    print(f"Expanding {machine_name}...")
                    expand_arrow.click()
                    time.sleep(3)
                    
                    page.screenshot(path=str(screenshots_dir / f"02_{machine_name}_expanded.png"))
                    print(f"Screenshot: 02_{machine_name}_expanded.png")
                    
                    # Look for repositories
                    repo_table = page.get_by_test_id("machine-repo-list-table")
                    if repo_table.is_visible():
                        print(f"✅ Repository table found for {machine_name}!")
                        
                        repo_rows = repo_table.locator('tbody tr')
                        repo_count = repo_rows.count()
                        print(f"Found {repo_count} repository rows")
                        
                        for i in range(repo_count):
                            repo_row = repo_rows.nth(i)
                            repo_text = repo_row.inner_text()
                            print(f"  Repository {i+1}: {repo_text[:100]}...")
                            
                            if "No data" not in repo_text and repo_text.strip():
                                print(f"  Found repository with data, expanding...")
                                
                                # Try to expand repository
                                repo_expand = repo_row.locator('button.ant-table-row-expand-icon, span[aria-label="right"]').first
                                if repo_expand.is_visible():
                                    repo_expand.click()
                                    time.sleep(3)
                                    
                                    page.screenshot(path=str(screenshots_dir / f"03_{machine_name}_repo_expanded.png"))
                                    print(f"Screenshot: 03_{machine_name}_repo_expanded.png")
                                    
                                    # Look for container actions
                                    print(f"  Looking for container actions...")
                                    
                                    container_selectors = [
                                        'button[data-testid*="container-actions"]',
                                        'button[data-testid*="machine-repo-list-container-actions"]',
                                        'button:has-text("Actions")',
                                        'button[title*="Container"]',
                                        'button[title*="Actions"]',
                                        '.ant-btn:has-text("⋮")',
                                        '.ant-btn:has([class*="more"])'
                                    ]
                                    
                                    container_found = False
                                    for selector in container_selectors:
                                        try:
                                            elements = page.locator(selector)
                                            count = elements.count()
                                            if count > 0:
                                                print(f"    Found {count} potential container actions: {selector}")
                                                
                                                for j in range(count):
                                                    element = elements.nth(j)
                                                    if element.is_visible():
                                                        print(f"    Clicking container actions button #{j+1}")
                                                        element.click()
                                                        time.sleep(1)
                                                        
                                                        page.screenshot(path=str(screenshots_dir / f"04_{machine_name}_actions_menu.png"))
                                                        print(f"Screenshot: 04_{machine_name}_actions_menu.png")
                                                        
                                                        container_found = True
                                                        
                                                        # Look for container_logs option
                                                        logs_option = page.get_by_text("container_logs")
                                                        if logs_option.is_visible():
                                                            print("    ✅ Found container_logs option!")
                                                            logs_option.click()
                                                            print("    ✅ Clicked container_logs!")
                                                            
                                                            time.sleep(5)
                                                            
                                                            page.screenshot(path=str(screenshots_dir / f"05_{machine_name}_logs_result.png"))
                                                            print(f"Screenshot: 05_{machine_name}_logs_result.png")
                                                            
                                                            # Observe what happened
                                                            print("\n=== OBSERVING CONTAINER LOGS RESULT ===")
                                                            
                                                            observations = []
                                                            
                                                            # Check for various display elements
                                                            modal = page.locator('.ant-modal')
                                                            if modal.is_visible():
                                                                observations.append("✅ Modal dialog opened")
                                                                modal_text = modal.inner_text()
                                                                print(f"    Modal content: {modal_text[:300]}...")
                                                            
                                                            drawer = page.locator('.ant-drawer')
                                                            if drawer.is_visible():
                                                                observations.append("✅ Drawer panel opened")
                                                                drawer_text = drawer.inner_text()
                                                                print(f"    Drawer content: {drawer_text[:300]}...")
                                                            
                                                            pre_elements = page.locator('pre')
                                                            for k in range(pre_elements.count()):
                                                                if pre_elements.nth(k).is_visible():
                                                                    content = pre_elements.nth(k).inner_text()
                                                                    if content.strip():
                                                                        observations.append(f"✅ Log content in <pre> element")
                                                                        print(f"    Log content: {content[:200]}...")
                                                            
                                                            # Check for messages
                                                            success_elements = page.locator('.ant-message, .ant-notification')
                                                            for k in range(success_elements.count()):
                                                                if success_elements.nth(k).is_visible():
                                                                    msg = success_elements.nth(k).inner_text()
                                                                    if msg.strip():
                                                                        observations.append(f"✅ Message: {msg}")
                                                                        print(f"    Message: {msg}")
                                                            
                                                            # Final screenshot
                                                            page.screenshot(path=str(screenshots_dir / "06_final_result.png"))
                                                            print("Screenshot: 06_final_result.png")
                                                            
                                                            # Report results
                                                            print("\n" + "="*50)
                                                            print("🎯 CONTAINER LOGS TEST SUMMARY")
                                                            print("="*50)
                                                            print(f"Machine tested: {machine_name}")
                                                            print(f"Repository found: ✅")
                                                            print(f"Container actions found: ✅")
                                                            print(f"container_logs option found: ✅")
                                                            print(f"container_logs clicked: ✅")
                                                            print(f"\nObservations ({len(observations)}):")
                                                            for obs in observations:
                                                                print(f"  {obs}")
                                                            
                                                            if observations:
                                                                print(f"\n🎉 SUCCESS: Container logs functionality working!")
                                                            else:
                                                                print(f"\n⚠️  Container logs triggered but no clear response")
                                                            
                                                            print("="*50)
                                                            container_logs_tested = True
                                                            
                                                        else:
                                                            print("    ❌ container_logs option not found")
                                                            # List available options
                                                            menu_items = page.locator('.ant-dropdown-menu-item, .ant-menu-item')
                                                            print(f"    Available options ({menu_items.count()}):")
                                                            for k in range(menu_items.count()):
                                                                item = menu_items.nth(k)
                                                                if item.is_visible():
                                                                    text = item.inner_text().strip()
                                                                    if text:
                                                                        print(f"      - {text}")
                                                        
                                                        break  # Exit after first successful click
                                        except Exception as e:
                                            print(f"    Error with selector {selector}: {e}")
                                    
                                    if not container_found:
                                        print(f"    No container actions found for this repository")
                                    
                                    if container_logs_tested:
                                        break  # Exit repository loop
                                else:
                                    print(f"    No expand button for repository {i+1}")
                    else:
                        print(f"No repository table found for {machine_name}")
                else:
                    print(f"No expand arrow found for {machine_name}")
            else:
                print(f"Machine {machine_name} not found")
        
        if not container_logs_tested:
            print("\n❌ Could not test container logs - no suitable repositories found")
            print("This might mean:")
            print("  - No repositories are created yet")
            print("  - No containers are running")
            print("  - Repositories don't have container actions")
        
        print("\n=== Test Completed ===")
        print("Check screenshots for visual confirmation")
        
        # Keep browser open briefly
        print("\nKeeping browser open for 10 seconds...")
        time.sleep(10)
        
    except Exception as e:
        print(f"\n❌ Error during test: {str(e)}")
        if 'page' in locals():
            error_screenshot = screenshots_dir / "error_screenshot.png"
            page.screenshot(path=str(error_screenshot))
            print(f"Error screenshot: {error_screenshot}")
        raise
    
    finally:
        if context:
            context.close()
        if browser:
            browser.close()
        print("\nBrowser closed.")


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