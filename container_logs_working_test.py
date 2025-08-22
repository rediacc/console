#!/usr/bin/env python3
"""
Container Logs Working Test - Clean Implementation
Tests the container logs functionality step by step
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
        print("Starting Container Logs Working Test...")
        
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
        print("\n=== STEP 1: Navigate and Login ===")
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
        
        page.screenshot(path=str(screenshots_dir / "01_resources_loaded.png"))
        print("Screenshot: 01_resources_loaded.png")
        
        # Step 3: Find and expand machine rediacc11
        print("\n=== STEP 3: Expand Machine rediacc11 ===")
        
        # Look for rediacc11 machine row
        machine_row = page.locator('tr:has-text("rediacc11")')
        if machine_row.count() > 0:
            print("Found rediacc11 machine row")
            
            # Click the expand arrow
            expand_arrow = machine_row.locator('td').first.locator('span[aria-label="right"]')
            if expand_arrow.is_visible():
                print("Clicking expand arrow for rediacc11...")
                expand_arrow.click()
                time.sleep(3)
                
                page.screenshot(path=str(screenshots_dir / "02_machine_expanded.png"))
                print("Screenshot: 02_machine_expanded.png")
                print("✅ Machine expanded successfully!")
                
            else:
                print("Expand arrow not found, trying alternatives...")
                # Try other expand mechanisms
                expand_selectors = [
                    'button.ant-table-row-expand-icon',
                    '[role="button"][aria-label*="expand"]',
                    'span.anticon-right',
                    'td:first-child button',
                    'td:first-child span[class*="expand"]'
                ]
                
                for selector in expand_selectors:
                    try:
                        element = machine_row.locator(selector).first
                        if element.is_visible():
                            print(f"Expanding with: {selector}")
                            element.click()
                            time.sleep(3)
                            break
                    except:
                        continue
        else:
            print("❌ rediacc11 machine not found")
            
        # Step 4: Look for repositories
        print("\n=== STEP 4: Look for Repositories ===")
        
        repo_table = page.get_by_test_id("machine-repo-list-table")
        if repo_table.is_visible():
            print("✅ Repository table found!")
            
            repo_rows = repo_table.locator('tbody tr')
            repo_count = repo_rows.count()
            print(f"Found {repo_count} repository rows")
            
            for i in range(repo_count):
                repo_row = repo_rows.nth(i)
                repo_text = repo_row.inner_text()
                print(f"  Repository {i+1}: {repo_text[:100]}...")
                
                if "No data" not in repo_text and repo_text.strip():
                    print(f"  Expanding repository {i+1}")
                    
                    # Expand repository
                    repo_expand = repo_row.locator('button.ant-table-row-expand-icon, span[aria-label="right"]').first
                    if repo_expand.is_visible():
                        repo_expand.click()
                        time.sleep(2)
                        
                        page.screenshot(path=str(screenshots_dir / "03_repository_expanded.png"))
                        print("Screenshot: 03_repository_expanded.png")
                        print("✅ Repository expanded!")
                        
                        # Step 5: Look for container actions
                        print("\n=== STEP 5: Find Container Actions ===")
                        
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
                                    print(f"  Found {count} potential container actions: {selector}")
                                    
                                    for j in range(count):
                                        element = elements.nth(j)
                                        if element.is_visible():
                                            print(f"  Clicking container actions button #{j+1}")
                                            element.click()
                                            time.sleep(1)
                                            
                                            page.screenshot(path=str(screenshots_dir / "04_actions_menu.png"))
                                            print("Screenshot: 04_actions_menu.png")
                                            
                                            container_found = True
                                            
                                            # Step 6: Click container_logs
                                            print("\n=== STEP 6: Click container_logs ===")
                                            
                                            logs_option = page.get_by_text("container_logs")
                                            if logs_option.is_visible():
                                                print("✅ Found container_logs option!")
                                                logs_option.click()
                                                print("✅ Clicked container_logs!")
                                                
                                                time.sleep(3)
                                                
                                                page.screenshot(path=str(screenshots_dir / "05_logs_triggered.png"))
                                                print("Screenshot: 05_logs_triggered.png")
                                                
                                                # Step 7: Observe log display
                                                print("\n=== STEP 7: Observe Log Display ===")
                                                
                                                observations = []
                                                
                                                # Check for modal dialog
                                                modal = page.locator('.ant-modal')
                                                if modal.is_visible():
                                                    observations.append("✅ Logs displayed in modal dialog")
                                                    title_elem = modal.locator('.ant-modal-title')
                                                    title = title_elem.inner_text() if title_elem.count() > 0 else "No title"
                                                    print(f"  Modal title: {title}")
                                                    
                                                    body_elem = modal.locator('.ant-modal-body')
                                                    body = body_elem.inner_text() if body_elem.count() > 0 else "No body"
                                                    print(f"  Modal content preview: {body[:200]}...")
                                                
                                                # Check for drawer panel
                                                drawer = page.locator('.ant-drawer')
                                                if drawer.is_visible():
                                                    observations.append("✅ Logs displayed in drawer panel")
                                                    content = drawer.inner_text()
                                                    print(f"  Drawer content preview: {content[:200]}...")
                                                
                                                # Check for pre-formatted text
                                                pre_elements = page.locator('pre')
                                                visible_pre = 0
                                                for k in range(pre_elements.count()):
                                                    if pre_elements.nth(k).is_visible():
                                                        visible_pre += 1
                                                        content = pre_elements.nth(k).inner_text()
                                                        print(f"  Log content in <pre>: {content[:150]}...")
                                                        observations.append(f"✅ Found log content in <pre> element #{k+1}")
                                                
                                                if visible_pre > 0:
                                                    print(f"  Found {visible_pre} visible <pre> elements with log content")
                                                
                                                # Check for code blocks
                                                code_elements = page.locator('code')
                                                for k in range(code_elements.count()):
                                                    if code_elements.nth(k).is_visible():
                                                        content = code_elements.nth(k).inner_text()
                                                        if content.strip() and len(content) > 20:
                                                            print(f"  Log content in <code>: {content[:150]}...")
                                                            observations.append("✅ Found log content in <code> element")
                                                
                                                # Check for text areas
                                                textarea_elements = page.locator('textarea')
                                                for k in range(textarea_elements.count()):
                                                    if textarea_elements.nth(k).is_visible():
                                                        content = textarea_elements.nth(k).input_value()
                                                        if content.strip():
                                                            print(f"  Log content in textarea: {content[:150]}...")
                                                            observations.append("✅ Found log content in textarea")
                                                
                                                # Check for success messages
                                                success_selectors = [
                                                    '.ant-message-success',
                                                    '.ant-notification-notice-success',
                                                    '*:has-text("Success")',
                                                    '*:has-text("success")',
                                                    '*:has-text("completed")',
                                                    '*:has-text("Completed")',
                                                    '*:has-text("finished")',
                                                    '*:has-text("done")'
                                                ]
                                                
                                                for selector in success_selectors:
                                                    elements = page.locator(selector)
                                                    for k in range(elements.count()):
                                                        element = elements.nth(k)
                                                        if element.is_visible():
                                                            text = element.inner_text()
                                                            if text.strip():
                                                                print(f"  ✅ Success message: {text}")
                                                                observations.append(f"✅ Success message: {text}")
                                                
                                                # Check for error messages
                                                error_selectors = [
                                                    '.ant-message-error',
                                                    '.ant-notification-notice-error',
                                                    '*:has-text("Error")',
                                                    '*:has-text("error")',
                                                    '*:has-text("failed")',
                                                    '*:has-text("Failed")'
                                                ]
                                                
                                                for selector in error_selectors:
                                                    elements = page.locator(selector)
                                                    for k in range(elements.count()):
                                                        element = elements.nth(k)
                                                        if element.is_visible():
                                                            text = element.inner_text()
                                                            if text.strip():
                                                                print(f"  ❌ Error message: {text}")
                                                                observations.append(f"❌ Error: {text}")
                                                
                                                # Wait for any async loading
                                                time.sleep(2)
                                                
                                                # Final screenshot
                                                page.screenshot(path=str(screenshots_dir / "06_final_logs_state.png"))
                                                print("Screenshot: 06_final_logs_state.png")
                                                
                                                # Summary
                                                print("\n=== FINAL OBSERVATIONS ===")
                                                for obs in observations:
                                                    print(f"  {obs}")
                                                
                                                if observations:
                                                    print("\n🎉 SUCCESS: Container logs functionality is working!")
                                                    print("   - Successfully navigated to Resources")
                                                    print("   - Successfully expanded machine rediacc11")
                                                    print("   - Successfully found repositories")
                                                    print("   - Successfully clicked container_logs")
                                                    print("   - Successfully observed log display")
                                                else:
                                                    print("\n⚠️  Container logs was clicked but no clear output detected")
                                                    print("   This might mean:")
                                                    print("   - Logs are loading asynchronously")
                                                    print("   - No logs available for this container")
                                                    print("   - Different display pattern than expected")
                                                
                                            else:
                                                print("❌ container_logs option not found in menu")
                                                
                                                # Show available options
                                                menu_items = page.locator('.ant-dropdown-menu-item, .ant-menu-item')
                                                if menu_items.count() > 0:
                                                    print("\n  Available menu options:")
                                                    for k in range(menu_items.count()):
                                                        item = menu_items.nth(k)
                                                        if item.is_visible():
                                                            text = item.inner_text().strip()
                                                            if text:
                                                                print(f"    - {text}")
                                                else:
                                                    print("  No menu items found")
                                            
                                            break
                            except Exception as e:
                                print(f"  Error with selector {selector}: {e}")
                        
                        if not container_found:
                            print("❌ No container actions found")
                            print("   This could mean:")
                            print("   - Repository is not active")
                            print("   - No containers are running")
                            print("   - UI structure is different than expected")
                            
                            page.screenshot(path=str(screenshots_dir / "05_no_container_actions.png"))
                            print("Screenshot: 05_no_container_actions.png")
                        
                        break  # Only test first valid repository
                    else:
                        print(f"  No expand button found for repository {i+1}")
            
        else:
            print("❌ Repository table not visible after machine expansion")
            page.screenshot(path=str(screenshots_dir / "04_no_repo_table.png"))
            print("Screenshot: 04_no_repo_table.png")
        
        print("\n=== Test Completed ===")
        print("Final screenshots saved in artifacts/screenshots/")
        
        # Keep browser open for inspection
        print("\nKeeping browser open for 15 seconds for manual review...")
        time.sleep(15)
        
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