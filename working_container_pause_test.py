#!/usr/bin/env python3
"""
Working Container Pause Test
Tests the container pause functionality with proper login handling
"""

import time
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from datetime import datetime


def run():
    with sync_playwright() as p:
        browser = None
        try:
            print("Starting Working Container Pause Test...")
            
            # Launch browser
            browser = p.chromium.launch(headless=False, args=['--start-maximized'])
            context = browser.new_context(viewport={'width': 1440, 'height': 900})
            page = context.new_page()
            
            # Setup logging
            network_logs = []
            console_logs = []
            
            def log_request(request):
                network_logs.append({
                    'type': 'request',
                    'method': request.method,
                    'url': request.url,
                    'timestamp': datetime.now().isoformat()
                })
                
            def log_response(response):
                network_logs.append({
                    'type': 'response',
                    'status': response.status,
                    'url': response.url,
                    'timestamp': datetime.now().isoformat()
                })
                
            def log_console(msg):
                console_logs.append({
                    'type': msg.type,
                    'text': msg.text,
                    'timestamp': datetime.now().isoformat()
                })
            
            page.on('request', log_request)
            page.on('response', log_response)
            page.on('console', log_console)
            
            page.set_default_timeout(30000)
            
            # Step 1: Navigate to console
            print("\n=== STEP 1: Navigation ===")
            page.goto("http://localhost:7322/console")
            time.sleep(2)
            
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step1_navigation.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            print(f"Current URL: {page.url}")
            
            # Step 2: Login
            print("\n=== STEP 2: Login ===")
            
            # Find and fill email input (it's a text input, not email type)
            email_input = page.locator('input[placeholder*="email"]').first
            email_input.fill("admin@rediacc.io")
            print("Email filled")
            
            # Find and fill password input
            password_input = page.locator('input[type="password"]').first
            password_input.fill("admin")
            print("Password filled")
            
            # Click Sign In button
            sign_in_button = page.locator('button:has-text("Sign In")').first
            sign_in_button.click()
            print("Sign In button clicked")
            
            # Wait for dashboard
            page.wait_for_url("**/dashboard", timeout=15000)
            time.sleep(2)
            
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step2_dashboard.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            print("Login successful!")
            
            # Step 3: Navigate to Resources
            print("\n=== STEP 3: Navigate to Resources ===")
            resources_link = page.get_by_test_id("main-nav-resources")
            resources_link.click()
            time.sleep(3)  # Wait for resources to load
            
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step3_resources.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            
            # Step 4: Find and expand machine
            print("\n=== STEP 4: Machine Expansion ===")
            
            # Look for machines in the table
            machine_rows = page.locator('tr').filter(has_text='rediacc').all()
            print(f"Found {len(machine_rows)} machine rows")
            
            if len(machine_rows) == 0:
                print("No machines found. Checking for data loading...")
                time.sleep(5)
                machine_rows = page.locator('tr').filter(has_text='rediacc').all()
                print(f"After wait, found {len(machine_rows)} machine rows")
            
            if len(machine_rows) > 0:
                # Look for expand button (usually a small arrow/plus icon)
                # Try different strategies to find the expand button
                expand_buttons = []
                
                # Strategy 1: Look for specific expand icons
                expand_icons = page.locator('.anticon-right, .ant-table-row-expand-icon').all()
                expand_buttons.extend(expand_icons)
                
                # Strategy 2: Look for buttons in machine rows that might be expand buttons
                for row in machine_rows:
                    row_buttons = row.locator('button').all()
                    for btn in row_buttons:
                        # Check if button looks like an expand button (small, no text, etc.)
                        btn_text = btn.inner_text().strip()
                        if not btn_text or len(btn_text) < 3:  # Likely an icon button
                            expand_buttons.append(btn)
                
                print(f"Found {len(expand_buttons)} potential expand buttons")
                
                if len(expand_buttons) > 0:
                    # Click the first expand button
                    expand_button = expand_buttons[0]
                    if expand_button.is_visible():
                        expand_button.click()
                        time.sleep(2)  # Wait for expansion
                        print("Machine expanded")
                    else:
                        print("Expand button not visible")
                else:
                    print("No expand buttons found")
            else:
                print("No machines found to expand")
            
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step4_machine_expanded.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            
            # Step 5: Look for repositories
            print("\n=== STEP 5: Repository Search ===")
            time.sleep(2)  # Wait for repos to load
            
            # Look for repository indicators
            repo_section = page.locator('text="Repositories"').count()
            repo_names = page.locator('text~="repo_"').count()
            print(f"Repository section found: {repo_section > 0}")
            print(f"Repository names found: {repo_names}")
            
            # Look for any table rows that might contain repositories
            all_rows = page.locator('tr').all()
            repo_rows = []
            for row in all_rows:
                row_text = row.inner_text().lower()
                if 'repo_' in row_text or 'repository' in row_text:
                    repo_rows.append(row)
            
            print(f"Found {len(repo_rows)} repository-related rows")
            
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step5_repositories.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            
            # Step 6: Look for container action buttons
            print("\n=== STEP 6: Container Actions Search ===")
            
            # Look for fx buttons (container actions)
            fx_buttons = page.locator('button:has-text("fx")').all()
            print(f"Found {len(fx_buttons)} fx buttons")
            
            # Look for buttons with container-related data-testid
            container_buttons = page.locator('[data-testid*="container"]').all()
            print(f"Found {len(container_buttons)} container buttons")
            
            # Look for any buttons that might be container actions
            all_buttons = page.locator('button').all()
            potential_container_buttons = []
            
            for button in all_buttons:
                if button.is_visible():
                    text = button.inner_text().strip()
                    testid = button.get_attribute('data-testid') or ''
                    title = button.get_attribute('title') or ''
                    
                    if (text == 'fx' or 
                        'container' in testid.lower() or 
                        'container' in title.lower()):
                        potential_container_buttons.append((button, text, testid, title))
            
            print(f"Found {len(potential_container_buttons)} potential container buttons:")
            for i, (btn, text, testid, title) in enumerate(potential_container_buttons):
                print(f"  {i+1}: '{text}' (testid: {testid}, title: {title})")
            
            if len(potential_container_buttons) > 0:
                # Click the first container button
                button_to_click = potential_container_buttons[0][0]
                print(f"\nClicking container button: {potential_container_buttons[0][1]}")
                button_to_click.click()
                time.sleep(1)  # Wait for menu
                
                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step6_container_menu.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"Screenshot: {screenshot_path}")
                
                # Step 7: Look for pause option
                print("\n=== STEP 7: Container Pause Action ===")
                
                # Look for pause option in the dropdown menu
                pause_elements = []
                
                # Various ways to find pause option
                pause_selectors = [
                    'text="container_pause"',
                    'text="pause"',
                    'li:has-text("pause")',
                    '.ant-dropdown-menu-item:has-text("pause")',
                    '[role="menuitem"]:has-text("pause")'
                ]
                
                for selector in pause_selectors:
                    elements = page.locator(selector).all()
                    for elem in elements:
                        if elem.is_visible():
                            pause_elements.append(elem)
                
                print(f"Found {len(pause_elements)} pause elements")
                
                # Also show what menu items are available
                menu_items = page.locator('li:visible, .ant-dropdown-menu-item:visible').all()
                available_items = []
                for item in menu_items:
                    text = item.inner_text().strip()
                    if text:
                        available_items.append(text)
                
                print(f"Available menu items: {available_items}")
                
                if len(pause_elements) > 0:
                    print("Clicking pause option...")
                    pause_element = pause_elements[0]
                    pause_element.click()
                    print("Container pause action clicked!")
                    
                    time.sleep(3)  # Wait for action to complete
                    
                    screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step7_after_pause.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"Screenshot: {screenshot_path}")
                    
                    # Step 8: Check for results
                    print("\n=== STEP 8: Results Check ===")
                    
                    # Look for notifications
                    notifications = page.locator('.ant-notification, .ant-message, .toast').all()
                    for notification in notifications:
                        if notification.is_visible():
                            text = notification.inner_text()
                            print(f"Notification: {text}")
                    
                    # Check for success/error messages
                    messages = page.locator('[class*="success"], [class*="error"], [class*="message"]').all()
                    for message in messages:
                        if message.is_visible():
                            text = message.inner_text()
                            if text.strip():
                                print(f"Message: {text}")
                    
                    # Check console logs for pause-related messages
                    pause_console_msgs = [msg for msg in console_logs if 'pause' in msg['text'].lower()]
                    if pause_console_msgs:
                        print(f"Console messages about pause ({len(pause_console_msgs)}):")
                        for msg in pause_console_msgs[-5:]:  # Show last 5
                            print(f"  [{msg['type']}] {msg['text']}")
                    
                    # Check network requests for pause-related API calls
                    pause_requests = [log for log in network_logs if 'pause' in log['url'].lower() or 'container' in log['url'].lower()]
                    if pause_requests:
                        print(f"Network requests related to pause/container ({len(pause_requests)}):")
                        for req in pause_requests[-5:]:  # Show last 5
                            print(f"  {req['method']} {req['url']} -> {req.get('status', 'pending')}")
                    
                else:
                    print("No pause option found in menu")
                    if available_items:
                        print(f"Available options were: {', '.join(available_items)}")
            else:
                print("No container action buttons found")
            
            # Final screenshot
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "step8_final.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            
            # Save logs
            logs_path = Path(__file__).parent / "artifacts" / "logs" / "working_test_logs.json"
            logs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(logs_path, 'w') as f:
                json.dump({
                    'network_logs': network_logs,
                    'console_logs': console_logs
                }, f, indent=2)
            print(f"Logs saved: {logs_path}")
            
            print("\n=== TEST COMPLETED ===")
            time.sleep(8)  # Keep browser open for inspection
            
        except Exception as e:
            print(f"\nError: {str(e)}")
            if 'page' in locals():
                error_screenshot = Path(__file__).parent / "artifacts" / "screenshots" / "error_working.png"
                error_screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(error_screenshot), full_page=True)
                print(f"Error screenshot: {error_screenshot}")
            raise
            
        finally:
            if browser:
                browser.close()
            print("Browser closed.")


if __name__ == "__main__":
    run()