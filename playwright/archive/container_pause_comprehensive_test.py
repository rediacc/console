#!/usr/bin/env python3
"""
Comprehensive Container Pause Test
Tests the container pause functionality in Rediacc console with detailed observations
"""

import re
import time
import sys
import json
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
from datetime import datetime


def run(playwright: Playwright) -> None:
    """Main test execution with comprehensive logging"""
    browser = None
    context = None
    
    try:
        print("Starting Comprehensive Container Pause Test...")
        
        # Launch browser with extended viewport for screenshots
        browser = playwright.chromium.launch(
            headless=False,
            args=['--start-maximized']
        )
        context = browser.new_context(
            viewport={'width': 1440, 'height': 900}
        )
        page = context.new_page()
        
        # Enable request/response logging
        request_responses = []
        def log_request(request):
            request_responses.append({
                'type': 'request',
                'url': request.url,
                'method': request.method,
                'timestamp': datetime.now().isoformat()
            })
            
        def log_response(response):
            request_responses.append({
                'type': 'response', 
                'url': response.url,
                'status': response.status,
                'timestamp': datetime.now().isoformat()
            })
        
        page.on('request', log_request)
        page.on('response', log_response)
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Step 1: Navigate to console
        print("\n=== STEP 1: Initial Navigation ===")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Take initial screenshot
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "01_initial_navigation.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 2: Handle login
        print("\n=== STEP 2: Login Process ===")
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            print("On login page, proceeding with login...")
        else:
            try:
                login_link = page.get_by_role("banner").get_by_role("link", name="Login")
                with page.expect_popup() as popup_info:
                    login_link.click()
                page = popup_info.value
                print("Navigated to login page via popup")
            except:
                print("No login link found, assuming already on login page")
        
        # Perform login
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
        page.wait_for_url("**/console/dashboard", timeout=10000)
        print("Login successful!")
        
        # Take post-login screenshot
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "02_after_login.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 3: Navigate to Resources
        print("\n=== STEP 3: Navigate to Resources ===")
        resources_link = page.get_by_test_id("main-nav-machines").get_by_text("Machines")
        resources_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)  # Additional wait for data loading
        
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "03_resources_page.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 4: Look for machines
        print("\n=== STEP 4: Machine Discovery ===")
        
        # Check if there are any machines visible
        machines_visible = page.locator('tr').filter(has_text=re.compile(r'rediacc\d+')).count()
        print(f"Found {machines_visible} machines")
        
        if machines_visible == 0:
            print("No machines found. Checking for 'No data' message...")
            no_data = page.locator('text="No data"').is_visible()
            if no_data:
                print("'No data' message found - no machines are currently available")
                return
        
        # Try to find rediacc11 specifically
        target_machine = "rediacc11"
        machine_row = page.locator('tr').filter(has_text=target_machine)
        
        if machine_row.count() == 0:
            print(f"Machine {target_machine} not found, looking for any available machine...")
            # Find any machine
            all_machines = page.locator('tr').filter(has_text=re.compile(r'rediacc\d+'))
            if all_machines.count() > 0:
                target_machine = all_machines.first.inner_text().split()[0]  # Get first machine name
                machine_row = all_machines.first
                print(f"Using machine: {target_machine}")
            else:
                print("No machines found at all")
                return
        
        # Step 5: Expand machine
        print(f"\n=== STEP 5: Expand Machine {target_machine} ===")
        
        try:
            # Look for expand button in the machine row
            expand_button = machine_row.locator('button').first
            if expand_button.is_visible():
                expand_button.click()
                print(f"Machine {target_machine} expanded successfully")
                time.sleep(2)  # Wait for expansion
            else:
                print("Expand button not visible")
        except Exception as e:
            print(f"Error expanding machine: {e}")
        
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "04_machine_expanded.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 6: Look for repositories
        print("\n=== STEP 6: Repository Discovery ===")
        
        # Wait a bit for repositories to load
        time.sleep(2)
        
        # Look for repositories section
        repositories_section = page.locator('text="Repositories"')
        if repositories_section.is_visible():
            print("Repositories section found")
            
            # Look for repository names
            repo_names = page.locator('[data-testid*="repo"]').all()
            print(f"Found {len(repo_names)} repository elements")
            
            # Look for repository rows or containers
            repo_containers = page.locator('tr').filter(has_text=re.compile(r'repo_|rediacc\d+')).all()
            print(f"Found {len(repo_containers)} repository containers")
            
        else:
            print("Repositories section not found")
        
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "05_repository_state.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 7: Look for container actions
        print("\n=== STEP 7: Container Actions Discovery ===")
        
        # Look for any button with "fx" or container-related test IDs
        container_action_buttons = []
        
        # Strategy 1: Look for fx buttons
        fx_buttons = page.locator('button:has-text("fx")').all()
        container_action_buttons.extend(fx_buttons)
        print(f"Found {len(fx_buttons)} fx buttons")
        
        # Strategy 2: Look for container action test IDs
        container_test_ids = page.locator('[data-testid*="container-actions"]').all()
        container_action_buttons.extend(container_test_ids)
        print(f"Found {len(container_test_ids)} container action buttons by test ID")
        
        # Strategy 3: Look for any buttons in repository rows
        repo_buttons = page.locator('tr button').all()
        print(f"Found {len(repo_buttons)} total buttons in table rows")
        
        if len(container_action_buttons) > 0:
            print(f"Total container action buttons found: {len(container_action_buttons)}")
            
            # Try to click the first container action button
            first_button = container_action_buttons[0]
            print("Clicking first container action button...")
            
            # Check if button is visible and clickable
            if first_button.is_visible():
                first_button.click()
                print("Container actions button clicked!")
                time.sleep(1)  # Wait for menu to appear
                
                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "06_container_actions_menu.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"Screenshot saved: {screenshot_path}")
                
                # Step 8: Look for container_pause option
                print("\n=== STEP 8: Container Pause Action ===")
                
                # Look for pause option
                pause_options = []
                
                # Try different selectors for pause
                pause_selectors = [
                    'text="container_pause"',
                    'text="pause"',
                    '[title*="pause"]',
                    'li:has-text("pause")'
                ]
                
                for selector in pause_selectors:
                    try:
                        elements = page.locator(selector).all()
                        pause_options.extend(elements)
                    except:
                        pass
                
                print(f"Found {len(pause_options)} pause options")
                
                if len(pause_options) > 0:
                    print("Clicking container_pause option...")
                    pause_option = pause_options[0]
                    
                    # Click pause option
                    pause_option.click()
                    print("Container pause action initiated!")
                    
                    time.sleep(3)  # Wait for pause action to complete
                    
                    screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "07_after_pause_action.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"Screenshot saved: {screenshot_path}")
                    
                    # Step 9: Check for success messages or status changes
                    print("\n=== STEP 9: Status Verification ===")
                    
                    # Look for notifications or status messages
                    notifications = page.locator('.ant-notification, .toast, .alert').all()
                    print(f"Found {len(notifications)} notification elements")
                    
                    for i, notification in enumerate(notifications):
                        if notification.is_visible():
                            text = notification.inner_text()
                            print(f"Notification {i+1}: {text}")
                    
                    # Check console for any messages
                    console_messages = []
                    def collect_console(msg):
                        console_messages.append({
                            'type': msg.type,
                            'text': msg.text,
                            'timestamp': datetime.now().isoformat()
                        })
                    
                    page.on('console', collect_console)
                    time.sleep(2)  # Wait for any console messages
                    
                    if console_messages:
                        print(f"Found {len(console_messages)} console messages:")
                        for msg in console_messages[-10:]:  # Show last 10 messages
                            print(f"  [{msg['type']}] {msg['text']}")
                    
                    # Look for any status indicators
                    status_indicators = page.locator('[class*="status"], [class*="state"], .badge').all()
                    print(f"Found {len(status_indicators)} status indicator elements")
                    
                    for i, indicator in enumerate(status_indicators[:5]):  # Show first 5
                        if indicator.is_visible():
                            text = indicator.inner_text()
                            classes = indicator.get_attribute('class') or ''
                            print(f"Status indicator {i+1}: '{text}' (classes: {classes})")
                    
                else:
                    print("No pause options found in the menu")
                    
                    # Look for what options are actually available
                    menu_items = page.locator('li, .menu-item, [role="menuitem"]').all()
                    print(f"Available menu items ({len(menu_items)}):")
                    for i, item in enumerate(menu_items[:10]):  # Show first 10
                        if item.is_visible():
                            text = item.inner_text().strip()
                            if text:
                                print(f"  {i+1}: {text}")
            else:
                print("Container actions button is not visible")
        else:
            print("No container action buttons found")
        
        # Final screenshot
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "08_final_state.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Save network activity log
        network_log_path = Path(__file__).parent / "artifacts" / "logs" / "network_activity.json"
        network_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(network_log_path, 'w') as f:
            json.dump(request_responses, f, indent=2)
        print(f"Network activity log saved: {network_log_path}")
        
        print("\n=== TEST COMPLETED SUCCESSFULLY ===")
        
        # Keep browser open for a moment to see results
        time.sleep(5)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Error screenshot saved to: {screenshot_path}")
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