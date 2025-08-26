#!/usr/bin/env python3
"""
Final Container Pause Test
Tests the container pause functionality in Rediacc console with proper machine expansion
"""

import re
import time
import sys
import json
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
from datetime import datetime


def run(playwright: Playwright) -> None:
    """Main test execution with proper machine expansion"""
    browser = None
    context = None
    
    try:
        print("Starting Final Container Pause Test...")
        
        # Launch browser
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
        console_messages = []
        
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
            
        def log_console(msg):
            console_messages.append({
                'type': msg.type,
                'text': msg.text,
                'timestamp': datetime.now().isoformat()
            })
        
        page.on('request', log_request)
        page.on('response', log_response)
        page.on('console', log_console)
        
        # Set timeout
        page.set_default_timeout(30000)
        
        # Step 1: Navigate and login
        print("\n=== STEP 1: Navigate and Login ===")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        current_url = page.url
        if '/login' in current_url or current_url.endswith('/console/'):
            # Login process
            email_input = page.locator('input[type="email"]').first
            password_input = page.locator('input[type="password"]').first
            submit_button = page.locator('button[type="submit"]').first
            
            email_input.fill("admin@rediacc.io")
            password_input.fill("admin")
            submit_button.click()
            
            page.wait_for_url("**/console/dashboard", timeout=10000)
            print("Login successful!")
        
        # Step 2: Navigate to Resources
        print("\n=== STEP 2: Navigate to Resources ===")
        resources_link = page.get_by_test_id("main-nav-resources").get_by_text("Resources")
        resources_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "01_resources_loaded.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 3: Find and properly expand machine
        print("\n=== STEP 3: Machine Expansion ===")
        
        # Look for machine expand button (the arrow icon, not the machine name)
        expand_buttons = page.locator('button[class*="expand"], .ant-table-row-expand-icon').all()
        print(f"Found {len(expand_buttons)} potential expand buttons")
        
        if len(expand_buttons) > 0:
            # Click the first expand button
            expand_button = expand_buttons[0]
            if expand_button.is_visible():
                print("Clicking machine expand button...")
                expand_button.click()
                time.sleep(2)  # Wait for expansion
                
                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "02_machine_expanded.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"Screenshot saved: {screenshot_path}")
            else:
                print("Expand button not visible")
        else:
            # Alternative approach: look for expand icons
            expand_icons = page.locator('svg[class*="expand"], .anticon-right').all()
            print(f"Found {len(expand_icons)} expand icons")
            
            if len(expand_icons) > 0:
                expand_icon = expand_icons[0]
                expand_icon.click()
                time.sleep(2)
                
                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "02_machine_expanded_alt.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"Screenshot saved: {screenshot_path}")
        
        # Step 4: Look for repositories after expansion
        print("\n=== STEP 4: Repository Discovery ===")
        time.sleep(2)  # Wait for repositories to load
        
        # Look for repository section or repository table
        repo_indicators = [
            'text="Repositories"',
            'text="REPOSITORY NAME"', 
            '[class*="repository"]',
            'td:has-text("repo_")'
        ]
        
        repo_found = False
        for indicator in repo_indicators:
            elements = page.locator(indicator).all()
            if len(elements) > 0:
                print(f"Found repository indicator: {indicator} ({len(elements)} elements)")
                repo_found = True
        
        if not repo_found:
            print("No repository indicators found")
        
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "03_repositories_visible.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 5: Look for repository expand buttons
        print("\n=== STEP 5: Repository Expansion ===")
        
        # Look for repository-specific expand buttons
        repo_expand_buttons = []
        
        # Try various selectors for repository expand buttons
        repo_expand_selectors = [
            '.ant-table-row-expand-icon',
            'button[class*="expand"]',
            'svg[class*="right"]'
        ]
        
        for selector in repo_expand_selectors:
            buttons = page.locator(selector).all()
            repo_expand_buttons.extend(buttons)
        
        print(f"Found {len(repo_expand_buttons)} potential repository expand buttons")
        
        # Try to click a repository expand button
        for i, button in enumerate(repo_expand_buttons):
            if button.is_visible():
                try:
                    print(f"Clicking repository expand button {i+1}...")
                    button.click()
                    time.sleep(1)
                    break
                except:
                    continue
        
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "04_after_repo_expansion.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Step 6: Look for container action buttons (fx buttons)
        print("\n=== STEP 6: Container Actions Search ===")
        
        # Look for fx buttons or container action buttons
        fx_buttons = page.locator('button:has-text("fx")').all()
        print(f"Found {len(fx_buttons)} fx buttons")
        
        container_action_buttons = page.locator('[data-testid*="container-actions"]').all()
        print(f"Found {len(container_action_buttons)} container action buttons")
        
        # Look for any buttons that might be container-related
        all_buttons = page.locator('button').all()
        print(f"Total buttons on page: {len(all_buttons)}")
        
        # Check for buttons with specific text or attributes
        container_related_buttons = []
        for button in all_buttons:
            if button.is_visible():
                text = button.inner_text().strip()
                title = button.get_attribute('title') or ''
                data_testid = button.get_attribute('data-testid') or ''
                
                if ('fx' in text.lower() or 
                    'container' in title.lower() or 
                    'container' in data_testid.lower() or
                    text == 'fx'):
                    container_related_buttons.append((button, text, title, data_testid))
        
        print(f"Found {len(container_related_buttons)} container-related buttons:")
        for i, (button, text, title, testid) in enumerate(container_related_buttons[:5]):
            print(f"  {i+1}: text='{text}', title='{title}', testid='{testid}'")
        
        if len(container_related_buttons) > 0:
            # Click the first container-related button
            button_to_click = container_related_buttons[0][0]
            print("\n=== STEP 7: Click Container Actions Button ===")
            button_to_click.click()
            time.sleep(1)  # Wait for menu
            
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "05_container_menu_open.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot saved: {screenshot_path}")
            
            # Step 8: Look for pause option in the menu
            print("\n=== STEP 8: Container Pause Action ===")
            
            # Look for pause option in various ways
            pause_options = []
            
            pause_selectors = [
                'text="container_pause"',
                'text="pause"',
                'li:has-text("pause")',
                '[title*="pause"]',
                '.ant-dropdown-menu-item:has-text("pause")'
            ]
            
            for selector in pause_selectors:
                elements = page.locator(selector).all()
                for element in elements:
                    if element.is_visible():
                        pause_options.append(element)
            
            print(f"Found {len(pause_options)} pause options")
            
            # Also check what menu items are available
            menu_items = page.locator('li, .menu-item, [role="menuitem"], .ant-dropdown-menu-item').all()
            available_options = []
            for item in menu_items:
                if item.is_visible():
                    text = item.inner_text().strip()
                    if text:
                        available_options.append(text)
            
            print(f"Available menu options: {available_options}")
            
            if len(pause_options) > 0:
                print("Clicking container_pause option...")
                pause_option = pause_options[0]
                pause_option.click()
                print("Container pause action initiated!")
                
                time.sleep(3)  # Wait for action to complete
                
                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "06_after_pause_click.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"Screenshot saved: {screenshot_path}")
                
                # Step 9: Check for results
                print("\n=== STEP 9: Check for Results ===")
                
                # Look for notifications
                notifications = page.locator('.ant-notification, .ant-message, .toast, .alert').all()
                print(f"Found {len(notifications)} notification elements")
                
                for notification in notifications:
                    if notification.is_visible():
                        text = notification.inner_text()
                        print(f"Notification: {text}")
                
                # Check console messages
                recent_console = [msg for msg in console_messages if 'pause' in msg['text'].lower()]
                print(f"Found {len(recent_console)} console messages about pause:")
                for msg in recent_console:
                    print(f"  [{msg['type']}] {msg['text']}")
                
                # Check for any API calls related to pause
                pause_requests = [req for req in request_responses if 'pause' in req['url'].lower()]
                print(f"Found {len(pause_requests)} API requests related to pause:")
                for req in pause_requests:
                    print(f"  {req['method']} {req['url']} ({req.get('status', 'N/A')})")
                
            else:
                print("No pause option found in menu")
                print(f"Available options were: {', '.join(available_options)}")
        else:
            print("No container action buttons found")
        
        # Final screenshot
        screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "07_final_state.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved: {screenshot_path}")
        
        # Save logs
        network_log_path = Path(__file__).parent / "artifacts" / "logs" / "network_activity_final.json"
        network_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(network_log_path, 'w') as f:
            json.dump({
                'requests_responses': request_responses,
                'console_messages': console_messages
            }, f, indent=2)
        print(f"Logs saved: {network_log_path}")
        
        print("\n=== TEST COMPLETED ===")
        time.sleep(5)  # Keep browser open
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        if 'page' in locals():
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_final.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Error screenshot: {screenshot_path}")
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