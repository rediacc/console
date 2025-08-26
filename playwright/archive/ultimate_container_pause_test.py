#!/usr/bin/env python3
"""
Ultimate Container Pause Test
Final comprehensive test for container pause functionality
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
            print("=== ULTIMATE CONTAINER PAUSE TEST ===")
            
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
            
            # Quick setup - login and navigate
            print("Step 1: Quick login and navigation...")
            page.goto("http://localhost:7322/console")
            time.sleep(2)
            
            # Login
            page.locator('input[placeholder*="email"]').first.fill("admin@rediacc.io")
            page.locator('input[type="password"]').first.fill("admin")
            page.locator('button:has-text("Sign In")').first.click()
            page.wait_for_url("**/dashboard", timeout=15000)
            
            # Go to Resources
            page.get_by_test_id("main-nav-resources").click()
            time.sleep(3)
            
            # Take initial screenshot
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "ultimate_start.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Initial state: {screenshot_path}")
            
            # Step 2: Find ALL buttons and analyze them
            print("\nStep 2: Analyzing all buttons on the page...")
            all_buttons = page.locator('button').all()
            print(f"Total buttons found: {len(all_buttons)}")
            
            fx_candidates = []
            for i, button in enumerate(all_buttons):
                if button.is_visible():
                    text = button.inner_text().strip()
                    classes = button.get_attribute('class') or ''
                    data_testid = button.get_attribute('data-testid') or ''
                    title = button.get_attribute('title') or ''
                    
                    # Look for fx or container-related buttons
                    if (text.lower() == 'fx' or 
                        'fx' in text.lower() or
                        'container' in classes.lower() or
                        'container' in data_testid.lower() or
                        'fx' in classes.lower()):
                        fx_candidates.append({
                            'index': i,
                            'button': button,
                            'text': text,
                            'classes': classes,
                            'testid': data_testid,
                            'title': title
                        })
            
            print(f"FX button candidates found: {len(fx_candidates)}")
            for candidate in fx_candidates:
                print(f"  Button {candidate['index']}: text='{candidate['text']}', classes='{candidate['classes']}', testid='{candidate['testid']}'")
            
            # If no obvious fx candidates, look for buttons in machine rows
            if len(fx_candidates) == 0:
                print("No obvious fx candidates. Looking for buttons in machine rows...")
                
                # Find machine rows
                machine_rows = page.locator('tr').filter(has_text='rediacc').all()
                print(f"Machine rows found: {len(machine_rows)}")
                
                for i, row in enumerate(machine_rows):
                    row_buttons = row.locator('button').all()
                    print(f"Machine row {i+1} has {len(row_buttons)} buttons")
                    
                    for j, btn in enumerate(row_buttons):
                        if btn.is_visible():
                            text = btn.inner_text().strip()
                            classes = btn.get_attribute('class') or ''
                            
                            # Add buttons from machine rows that might be fx buttons
                            if len(text) <= 3 or 'fx' in text.lower():  # Short text likely icons
                                fx_candidates.append({
                                    'index': f"row{i+1}_btn{j+1}",
                                    'button': btn,
                                    'text': text,
                                    'classes': classes,
                                    'testid': '',
                                    'title': ''
                                })
            
            print(f"Total fx candidates after machine row search: {len(fx_candidates)}")
            
            if len(fx_candidates) > 0:
                # Try clicking the first fx candidate
                print(f"\nStep 3: Clicking first fx candidate...")
                candidate = fx_candidates[0]
                print(f"Clicking button with text: '{candidate['text']}'")
                
                try:
                    candidate['button'].click()
                    time.sleep(2)  # Wait for dropdown
                    print("Button clicked successfully!")
                    
                    # Take screenshot after click
                    screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "ultimate_after_fx_click.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"After fx click: {screenshot_path}")
                    
                    # Step 4: Look for dropdown menu
                    print("\nStep 4: Analyzing dropdown menu...")
                    
                    # Wait a bit more for menu to appear
                    time.sleep(1)
                    
                    # Look for menu items with multiple strategies
                    menu_items = []
                    
                    # Strategy 1: Ant Design dropdown items
                    ant_items = page.locator('.ant-dropdown-menu-item:visible').all()
                    for item in ant_items:
                        text = item.inner_text().strip()
                        if text:
                            menu_items.append(('ant-dropdown', text, item))
                    
                    # Strategy 2: Generic menu items
                    generic_items = page.locator('li:visible, [role="menuitem"]:visible').all()
                    for item in generic_items:
                        text = item.inner_text().strip()
                        if text and not any(text in existing[1] for existing in menu_items):
                            menu_items.append(('generic', text, item))
                    
                    # Strategy 3: Any visible text that might be menu items
                    if len(menu_items) == 0:
                        print("No standard menu items found. Looking for any new visible text...")
                        # This is a fallback - look for any visible elements that appeared after click
                        time.sleep(1)
                        all_text_elements = page.locator('*:visible').all()
                        potential_menu_texts = []
                        for elem in all_text_elements[-20:]:  # Check last 20 elements (recently appeared)
                            text = elem.inner_text().strip()
                            if text and len(text) < 50:  # Reasonable menu item length
                                potential_menu_texts.append(text)
                        
                        print(f"Potential menu texts: {potential_menu_texts}")
                    
                    print(f"Menu items found: {len(menu_items)}")
                    for strategy, text, element in menu_items:
                        print(f"  [{strategy}] {text}")
                    
                    # Step 5: Look for pause option
                    print(f"\nStep 5: Looking for pause option...")
                    pause_found = False
                    
                    for strategy, text, element in menu_items:
                        if 'pause' in text.lower():
                            print(f"FOUND PAUSE OPTION: {text}")
                            pause_found = True
                            
                            try:
                                element.click()
                                print(f"Clicked pause option: {text}")
                                
                                time.sleep(4)  # Wait for action
                                
                                # Take screenshot after pause click
                                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "ultimate_after_pause.png"
                                page.screenshot(path=str(screenshot_path), full_page=True)
                                print(f"After pause click: {screenshot_path}")
                                
                                # Step 6: Check for results
                                print(f"\nStep 6: Checking for pause results...")
                                
                                # Look for any notifications or messages
                                notification_texts = []
                                notification_selectors = [
                                    '.ant-notification', '.ant-message', '.toast', '.alert',
                                    '[class*="success"]', '[class*="error"]', '[class*="notification"]'
                                ]
                                
                                for selector in notification_selectors:
                                    elements = page.locator(f'{selector}:visible').all()
                                    for elem in elements:
                                        text = elem.inner_text().strip()
                                        if text:
                                            notification_texts.append(f"{selector}: {text}")
                                
                                if notification_texts:
                                    print("SUCCESS! Found notification messages:")
                                    for msg in notification_texts:
                                        print(f"  ✅ {msg}")
                                else:
                                    print("No immediate notification messages found")
                                
                                # Check console for pause-related messages
                                pause_console = [log for log in console_logs 
                                               if 'pause' in log['text'].lower() or 'container' in log['text'].lower()]
                                if pause_console:
                                    print(f"Console activity related to pause ({len(pause_console)}):")
                                    for log in pause_console[-3:]:
                                        print(f"  📝 [{log['type']}] {log['text']}")
                                
                                # Check network for pause API calls
                                pause_network = [log for log in network_logs 
                                               if 'pause' in log['url'].lower() or 
                                                  ('container' in log['url'].lower() and log['type'] == 'request')]
                                if pause_network:
                                    print(f"Network requests related to pause ({len(pause_network)}):")
                                    for log in pause_network[-3:]:
                                        status = log.get('status', 'pending')
                                        print(f"  🌐 {log['method']} {log['url']} -> {status}")
                                
                                break
                                
                            except Exception as click_error:
                                print(f"Error clicking pause option: {click_error}")
                    
                    if not pause_found:
                        print("❌ No pause option found in menu")
                        if menu_items:
                            print("Available options were:")
                            for strategy, text, element in menu_items:
                                print(f"  - {text}")
                                
                            # Try clicking the first available option to see what happens
                            if len(menu_items) > 0:
                                print(f"\nTrying first available option: {menu_items[0][1]}")
                                try:
                                    menu_items[0][2].click()
                                    time.sleep(3)
                                    
                                    screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "ultimate_after_first_option.png"
                                    page.screenshot(path=str(screenshot_path), full_page=True)
                                    print(f"After clicking first option: {screenshot_path}")
                                except Exception as e:
                                    print(f"Error clicking first option: {e}")
                        else:
                            print("No menu options found at all")
                    
                except Exception as click_error:
                    print(f"Error clicking fx button: {click_error}")
                    
            else:
                print("❌ No fx button candidates found!")
            
            # Final screenshot
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "ultimate_final.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Final state: {screenshot_path}")
            
            # Save comprehensive logs
            logs_path = Path(__file__).parent / "artifacts" / "logs" / "ultimate_test_complete.json"
            logs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(logs_path, 'w') as f:
                json.dump({
                    'fx_candidates': [
                        {k: v for k, v in candidate.items() if k != 'button'}  # Remove non-serializable button object
                        for candidate in fx_candidates
                    ],
                    'network_logs': network_logs,
                    'console_logs': console_logs
                }, f, indent=2)
            print(f"Complete logs: {logs_path}")
            
            print(f"\n=== ULTIMATE TEST COMPLETED ===")
            time.sleep(8)  # Keep browser open for inspection
            
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            if 'page' in locals():
                error_screenshot = Path(__file__).parent / "artifacts" / "screenshots" / "ultimate_error.png"
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