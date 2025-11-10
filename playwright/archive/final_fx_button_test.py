#!/usr/bin/env python3
"""
Final FX Button Test
Tests clicking the fx (container actions) buttons to see what options are available
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
            print("Starting Final FX Button Test...")
            
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
            
            # Quick login
            print("Logging in...")
            page.goto("http://localhost:7322/console")
            time.sleep(2)
            
            email_input = page.locator('input[placeholder*="email"]').first
            email_input.fill("admin@rediacc.io")
            
            password_input = page.locator('input[type="password"]').first
            password_input.fill("admin")
            
            sign_in_button = page.locator('button:has-text("Sign In")').first
            sign_in_button.click()
            
            page.wait_for_url("**/dashboard", timeout=15000)
            print("Login successful!")
            
            # Navigate to Resources
            print("Navigating to Resources...")
            resources_link = page.get_by_test_id("main-nav-machines")
            resources_link.click()
            time.sleep(3)
            
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "fx_test_resources.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            
            # Look for FX buttons specifically
            print("\n=== FX BUTTON ANALYSIS ===")
            fx_buttons = page.locator('button:has-text("fx")').all()
            print(f"Found {len(fx_buttons)} fx buttons")
            
            if len(fx_buttons) > 0:
                # Click the first fx button
                print("Clicking first fx button...")
                fx_button = fx_buttons[0]
                fx_button.click()
                time.sleep(2)  # Wait for dropdown menu
                
                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "fx_menu_opened.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"Screenshot: {screenshot_path}")
                
                # Look for dropdown menu items
                print("\n=== DROPDOWN MENU ANALYSIS ===")
                
                # Various selectors for menu items
                menu_selectors = [
                    '.ant-dropdown-menu-item',
                    'li[role="menuitem"]',
                    '.ant-menu-item',
                    'li:visible',
                    '[role="menuitem"]'
                ]
                
                all_menu_items = []
                for selector in menu_selectors:
                    items = page.locator(selector).all()
                    for item in items:
                        if item.is_visible():
                            text = item.inner_text().strip()
                            if text and text not in all_menu_items:
                                all_menu_items.append(text)
                
                print(f"Menu items found: {all_menu_items}")
                
                # Look specifically for pause option
                pause_found = False
                pause_elements = []
                
                for item_text in all_menu_items:
                    if 'pause' in item_text.lower():
                        print(f"FOUND PAUSE OPTION: {item_text}")
                        pause_found = True
                        
                        # Find the actual element for this text
                        pause_element = page.locator(f'text="{item_text}"').first
                        if pause_element.is_visible():
                            pause_elements.append((pause_element, item_text))
                
                if pause_found and len(pause_elements) > 0:
                    print(f"\n=== CLICKING PAUSE OPTION ===")
                    pause_element, pause_text = pause_elements[0]
                    print(f"Clicking: {pause_text}")
                    
                    # Click the pause option
                    pause_element.click()
                    print("Pause option clicked!")
                    
                    time.sleep(4)  # Wait for action to complete
                    
                    screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "after_pause_click.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"Screenshot: {screenshot_path}")
                    
                    # Check for results
                    print("\n=== CHECKING FOR RESULTS ===")
                    
                    # Look for notifications, toasts, success messages
                    notification_selectors = [
                        '.ant-notification',
                        '.ant-message',
                        '.toast',
                        '.alert',
                        '[class*="success"]',
                        '[class*="error"]',
                        '[class*="notification"]'
                    ]
                    
                    found_messages = []
                    for selector in notification_selectors:
                        elements = page.locator(selector).all()
                        for elem in elements:
                            if elem.is_visible():
                                text = elem.inner_text().strip()
                                if text:
                                    found_messages.append(f"{selector}: {text}")
                    
                    if found_messages:
                        print("Found UI messages:")
                        for msg in found_messages:
                            print(f"  {msg}")
                    else:
                        print("No UI messages found")
                    
                    # Check console logs for pause-related activity
                    pause_console = [log for log in console_logs if 'pause' in log['text'].lower() or 'container' in log['text'].lower()]
                    if pause_console:
                        print(f"\nConsole messages about pause/container ({len(pause_console)}):")
                        for log in pause_console[-5:]:  # Last 5
                            print(f"  [{log['type']}] {log['text']}")
                    
                    # Check network activity for pause-related requests
                    pause_network = [log for log in network_logs 
                                   if 'pause' in log['url'].lower() or 'container' in log['url'].lower()]
                    if pause_network:
                        print(f"\nNetwork activity for pause/container ({len(pause_network)}):")
                        for log in pause_network[-5:]:  # Last 5
                            status = log.get('status', 'pending')
                            print(f"  {log['method']} {log['url']} -> {status}")
                    
                    # Look for status changes in the UI
                    print("\n=== CHECKING FOR STATUS CHANGES ===")
                    
                    # Look for any status indicators, badges, or state changes
                    status_selectors = [
                        '[class*="status"]',
                        '[class*="state"]',
                        '.badge',
                        '[class*="running"]',
                        '[class*="paused"]',
                        '[class*="stopped"]'
                    ]
                    
                    status_indicators = []
                    for selector in status_selectors:
                        elements = page.locator(selector).all()
                        for elem in elements:
                            if elem.is_visible():
                                text = elem.inner_text().strip()
                                classes = elem.get_attribute('class') or ''
                                if text or 'status' in classes or 'state' in classes:
                                    status_indicators.append(f"Text: '{text}', Classes: {classes}")
                    
                    if status_indicators:
                        print("Status indicators found:")
                        for indicator in status_indicators[:10]:  # Show first 10
                            print(f"  {indicator}")
                    else:
                        print("No status indicators found")
                    
                else:
                    print("No pause option found in menu")
                    print(f"Available options: {', '.join(all_menu_items) if all_menu_items else 'None visible'}")
                    
                    # Still show what we found
                    if all_menu_items:
                        print("\nLet's try clicking the first available option to see what happens...")
                        first_option = all_menu_items[0]
                        first_element = page.locator(f'text="{first_option}"').first
                        if first_element.is_visible():
                            print(f"Clicking: {first_option}")
                            first_element.click()
                            time.sleep(3)
                            
                            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "after_first_option.png"
                            page.screenshot(path=str(screenshot_path), full_page=True)
                            print(f"Screenshot: {screenshot_path}")
            else:
                print("No fx buttons found!")
            
            # Final screenshot
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "fx_test_final.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Final screenshot: {screenshot_path}")
            
            # Save all logs
            logs_path = Path(__file__).parent / "artifacts" / "logs" / "fx_test_complete.json"
            logs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(logs_path, 'w') as f:
                json.dump({
                    'network_logs': network_logs,
                    'console_logs': console_logs
                }, f, indent=2)
            print(f"Complete logs saved: {logs_path}")
            
            print("\n=== FX BUTTON TEST COMPLETED ===")
            time.sleep(10)  # Keep browser open longer for inspection
            
        except Exception as e:
            print(f"\nError: {str(e)}")
            if 'page' in locals():
                error_screenshot = Path(__file__).parent / "artifacts" / "screenshots" / "fx_test_error.png"
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