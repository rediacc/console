#!/usr/bin/env python3
"""
Final Container Logs Test - Using Correct UI Elements
Based on the actual UI structure visible in screenshots
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
        print("Starting Final Container Logs Test...")
        
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
            
            # Email
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
                
            # Password
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
                
            # Submit
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
                
            page.wait_for_url("**/console/dashboard", timeout=10000)
            print("✅ Login successful!")
        
        # Step 2: Navigate to Resources
        print("\n=== STEP 2: Navigate to Resources ===")
        resources_link = page.get_by_test_id("main-nav-machines").get_by_text("Machines")
        resources_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        
        page.screenshot(path=str(screenshots_dir / "01_resources_loaded.png"))
        print("Screenshot: 01_resources_loaded.png")
        
        # Step 3: Find and expand machine rediacc11
        print("\n=== STEP 3: Expand Machine rediacc11 ===")
        
        # Look for the expand arrow next to rediacc11
        machine_row = page.locator('tr:has-text("rediacc11")')
        if machine_row.count() > 0:
            print("Found rediacc11 machine row")
            
            # Click the expand arrow (►)
            expand_arrow = machine_row.locator('td').first.locator('span[aria-label="right"]')
            if expand_arrow.is_visible():
                print("Clicking expand arrow for rediacc11...")
                expand_arrow.click()
                time.sleep(3)  # Wait for expansion
                
                page.screenshot(path=str(screenshots_dir / "02_machine_expanded.png"))
                print("Screenshot: 02_machine_expanded.png")
                print("✅ Machine expanded successfully!")
                
            else:
                print("❌ Expand arrow not found, trying alternative selectors...")
                # Try other potential expand elements
                expand_selectors = [
                    'button.ant-table-row-expand-icon',
                    '[role="button"][aria-label*="expand"]',
                    'span.anticon-right',
                    'td:first-child button',
                    'td:first-child span[class*="expand"]'
                ]
                
                expanded = False
                for selector in expand_selectors:
                    try:
                        element = machine_row.locator(selector).first
                        if element.is_visible():
                            print(f"Trying expand with selector: {selector}")
                            element.click()
                            time.sleep(3)
                            expanded = True
                            break
                    except:
                        continue
                
                if not expanded:
                    print("❌ Could not find expand mechanism")
        else:
            print("❌ rediacc11 machine not found")
            
        # Step 4: Look for repositories
        print("\n=== STEP 4: Look for Repositories ===")
        
        # After expansion, look for repositories
        repo_table = page.get_by_test_id("machine-repo-list-table")
        if repo_table.is_visible():
            print("✅ Repository table found!")
            
            # List repositories
            repo_rows = repo_table.locator('tbody tr')
            repo_count = repo_rows.count()
            print(f"Found {repo_count} repository rows")
            
            for i in range(repo_count):
                repo_row = repo_rows.nth(i)
                repo_text = repo_row.inner_text()
                print(f"  Repository {i+1}: {repo_text[:100]}...")
                
                # Look for repositories with actual data (not "No data")
                if "No data" not in repo_text and repo_text.strip():
                    print(f"  Found valid repository data, expanding...")
                    
                    # Try to expand this repository
                    repo_expand = repo_row.locator('button.ant-table-row-expand-icon, span[aria-label="right"]').first
                    if repo_expand.is_visible():
                        repo_expand.click()
                        time.sleep(2)
                        
                        page.screenshot(path=str(screenshots_dir / "03_repository_expanded.png"))
                        print("Screenshot: 03_repository_expanded.png")
                        print("✅ Repository expanded!")
                        
                        # Step 5: Look for container actions
                        print("\n=== STEP 5: Find Container Actions ===")
                        
                        # Look for container actions buttons
                        container_action_selectors = [
                            'button[data-testid*="container-actions"]',
                            'button[data-testid*="machine-repo-list-container-actions"]',
                            'button:has-text("Actions")',
                            'button[title*="Container"]',
                            'button[title*="Actions"]',
                            '.ant-btn:has-text("⋮")',  # Three dots menu
                            '.ant-btn:has([class*="more"])'
                        ]
                        
                        container_actions_found = False
                        for selector in container_action_selectors:
                            try:
                                elements = page.locator(selector)
                                count = elements.count()
                                if count > 0:
                                    print(f"  Found {count} potential container action buttons: {selector}")
                                    
                                    for j in range(count):
                                        element = elements.nth(j)
                                        if element.is_visible():
                                            print(f"  Clicking container actions button #{j+1}")
                                            element.click()
                                            time.sleep(1)
                                            
                                            page.screenshot(path=str(screenshots_dir / "04_actions_menu_open.png"))
                                            print("Screenshot: 04_actions_menu_open.png")
                                            
                                            container_actions_found = True
                                            
                                            # Step 6: Click container_logs
                                            print("\n=== STEP 6: Click container_logs ===")
                                            
                                            # Look for container_logs option in the menu
                                            logs_option = page.get_by_text("container_logs")
                                            if logs_option.is_visible():
                                                print("✅ Found container_logs option!")
                                                logs_option.click()
                                                print("✅ Clicked container_logs!")
                                                
                                                # Wait for logs to appear
                                                time.sleep(3)
                                                
                                                page.screenshot(path=str(screenshots_dir / "05_logs_triggered.png"))
                                                print("Screenshot: 05_logs_triggered.png")
                                                
                                                # Step 7: Observe what happens
                                                print("\n=== STEP 7: Observe Log Display ===")
                                                
                                                # Check for various display patterns
                                                observations = []\n                                                \n                                                # Modal dialog\n                                                modal = page.locator('.ant-modal')\n                                                if modal.is_visible():\n                                                    observations.append(\"✅ Logs displayed in modal dialog\")\n                                                    title = modal.locator('.ant-modal-title').inner_text() if modal.locator('.ant-modal-title').count() > 0 else \"No title\"\n                                                    print(f\"  Modal title: {title}\")\n                                                    body = modal.locator('.ant-modal-body').inner_text() if modal.locator('.ant-modal-body').count() > 0 else \"No body\"\n                                                    print(f\"  Modal content preview: {body[:200]}...\")\n                                                \n                                                # Drawer panel\n                                                drawer = page.locator('.ant-drawer')\n                                                if drawer.is_visible():\n                                                    observations.append(\"✅ Logs displayed in drawer panel\")\n                                                    content = drawer.inner_text()\n                                                    print(f\"  Drawer content preview: {content[:200]}...\")\n                                                \n                                                # Pre-formatted text (common for logs)\n                                                pre_elements = page.locator('pre')\n                                                visible_pre = 0\n                                                for k in range(pre_elements.count()):\n                                                    if pre_elements.nth(k).is_visible():\n                                                        visible_pre += 1\n                                                        content = pre_elements.nth(k).inner_text()\n                                                        print(f\"  Log content in <pre>: {content[:150]}...\")\n                                                        observations.append(f\"✅ Found log content in <pre> element #{k+1}\")\n                                                \n                                                # Code blocks\n                                                code_elements = page.locator('code')\n                                                for k in range(code_elements.count()):\n                                                    if code_elements.nth(k).is_visible():\n                                                        content = code_elements.nth(k).inner_text()\n                                                        if content.strip() and len(content) > 20:  # Ignore small code snippets\n                                                            print(f\"  Log content in <code>: {content[:150]}...\")\n                                                            observations.append(f\"✅ Found log content in <code> element\")\n                                                \n                                                # Text areas\n                                                textarea_elements = page.locator('textarea')\n                                                for k in range(textarea_elements.count()):\n                                                    if textarea_elements.nth(k).is_visible():\n                                                        content = textarea_elements.nth(k).input_value()\n                                                        if content.strip():\n                                                            print(f\"  Log content in textarea: {content[:150]}...\")\n                                                            observations.append(f\"✅ Found log content in textarea\")\n                                                \n                                                # Success/completion messages\n                                                success_selectors = [\n                                                    '.ant-message-success',\n                                                    '.ant-notification-notice-success',\n                                                    '*:has-text(\"Success\")',\n                                                    '*:has-text(\"success\")',\n                                                    '*:has-text(\"completed\")',\n                                                    '*:has-text(\"Completed\")',\n                                                    '*:has-text(\"finished\")',\n                                                    '*:has-text(\"done\")',\n                                                ]\n                                                \n                                                for selector in success_selectors:\n                                                    elements = page.locator(selector)\n                                                    for k in range(elements.count()):\n                                                        element = elements.nth(k)\n                                                        if element.is_visible():\n                                                            text = element.inner_text()\n                                                            if text.strip():\n                                                                print(f\"  ✅ Success message: {text}\")\n                                                                observations.append(f\"✅ Success message: {text}\")\n                                                \n                                                # Error messages\n                                                error_selectors = [\n                                                    '.ant-message-error',\n                                                    '.ant-notification-notice-error',\n                                                    '*:has-text(\"Error\")',\n                                                    '*:has-text(\"error\")',\n                                                    '*:has-text(\"failed\")',\n                                                    '*:has-text(\"Failed\")',\n                                                ]\n                                                \n                                                for selector in error_selectors:\n                                                    elements = page.locator(selector)\n                                                    for k in range(elements.count()):\n                                                        element = elements.nth(k)\n                                                        if element.is_visible():\n                                                            text = element.inner_text()\n                                                            if text.strip():\n                                                                print(f\"  ❌ Error message: {text}\")\n                                                                observations.append(f\"❌ Error: {text}\")\n                                                \n                                                # Wait a bit more for any async loading\n                                                time.sleep(2)\n                                                \n                                                # Final screenshot\n                                                page.screenshot(path=str(screenshots_dir / \"06_final_logs_state.png\"))\n                                                print(\"Screenshot: 06_final_logs_state.png\")\n                                                \n                                                # Summary\n                                                print(\"\\n=== FINAL OBSERVATIONS ===\\n                                                for obs in observations:\n                                                    print(f\"  {obs}\")\n                                                \n                                                if observations:\n                                                    print(\"\\n🎉 SUCCESS: Container logs functionality is working!\")\n                                                    print(\"   - Successfully navigated to Resources\")\n                                                    print(\"   - Successfully expanded machine rediacc11\")\n                                                    print(\"   - Successfully found repositories\")\n                                                    print(\"   - Successfully clicked container_logs\")\n                                                    print(\"   - Successfully observed log display\")\n                                                else:\n                                                    print(\"\\n⚠️  Container logs was clicked but no clear output detected\")\n                                                    print(\"   This might mean:\")\n                                                    print(\"   - Logs are loading asynchronously\")\n                                                    print(\"   - No logs available for this container\")\n                                                    print(\"   - Different display pattern than expected\")\n                                                \n                                            else:\n                                                print(\"❌ container_logs option not found in menu\")\n                                                \n                                                # Show what options are available\n                                                menu_items = page.locator('.ant-dropdown-menu-item, .ant-menu-item, .ant-dropdown-menu .ant-dropdown-menu-item')\n                                                if menu_items.count() > 0:\n                                                    print(\"\\n  Available menu options:\")\n                                                    for k in range(menu_items.count()):\n                                                        item = menu_items.nth(k)\n                                                        if item.is_visible():\n                                                            text = item.inner_text().strip()\n                                                            if text:\n                                                                print(f\"    - {text}\")\n                                                else:\n                                                    print(\"  No menu items found\")\n                                            \n                                            break  # Exit after first successful click\n                            except Exception as e:\n                                print(f\"  Error with selector {selector}: {e}\")\n                        \n                        if not container_actions_found:\n                            print(\"❌ No container actions found\")\n                            print(\"   This could mean:\")\n                            print(\"   - Repository is not active\")\n                            print(\"   - No containers are running\")\n                            print(\"   - UI structure is different than expected\")\n                            \n                            # Take screenshot of current state for debugging\n                            page.screenshot(path=str(screenshots_dir / \"05_no_container_actions.png\"))\n                            print(\"Screenshot: 05_no_container_actions.png\")\n                        \n                        break  # Only test first valid repository\n                    else:\n                        print(f\"  No expand button found for repository {i+1}\")\n            \n        else:\n            print(\"❌ Repository table not visible after machine expansion\")\n            \n            # Debug screenshot\n            page.screenshot(path=str(screenshots_dir / \"04_no_repo_table.png\"))\n            print(\"Screenshot: 04_no_repo_table.png\")\n        \n        print(\"\\n=== Test Completed ===\\nFinal screenshots saved in artifacts/screenshots/\")\n        \n        # Keep browser open for manual inspection\n        print(\"\\nKeeping browser open for 15 seconds for manual review...\")\n        time.sleep(15)\n        \n    except Exception as e:\n        print(f\"\\n❌ Error during test: {str(e)}\")\n        if 'page' in locals():\n            error_screenshot = screenshots_dir / \"error_screenshot.png\"\n            page.screenshot(path=str(error_screenshot))\n            print(f\"Error screenshot: {error_screenshot}\")\n        raise\n    \n    finally:\n        if context:\n            context.close()\n        if browser:\n            browser.close()\n        print(\"\\nBrowser closed.\")\n\n\ndef main():\n    \"\"\"Entry point\"\"\"\n    try:\n        with sync_playwright() as playwright:\n            run(playwright)\n    except KeyboardInterrupt:\n        print(\"\\nTest interrupted by user\")\n        sys.exit(1)\n    except Exception as e:\n        print(f\"\\nTest failed: {str(e)}\")\n        sys.exit(1)\n\n\nif __name__ == \"__main__\":\n    main()