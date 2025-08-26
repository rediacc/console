#!/usr/bin/env python3
"""
Targeted FX Dropdown Test
Specifically targets the ant-dropdown-trigger button for container actions
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
            print("=== TARGETED FX DROPDOWN TEST ===")
            
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
            
            # Quick login and navigate
            print("🔐 Logging in and navigating to Resources...")
            page.goto("http://localhost:7322/console")
            time.sleep(2)
            
            page.locator('input[placeholder*="email"]').first.fill("admin@rediacc.io")
            page.locator('input[type="password"]').first.fill("admin")
            page.locator('button:has-text("Sign In")').first.click()
            page.wait_for_url("**/dashboard", timeout=15000)
            
            page.get_by_test_id("main-nav-resources").click()
            time.sleep(3)
            
            # Take initial screenshot
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "targeted_start.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"📸 Initial state: {screenshot_path}")
            
            # Look specifically for dropdown trigger buttons
            print(f"\n🎯 Looking for dropdown trigger buttons...")
            dropdown_triggers = page.locator('.ant-dropdown-trigger').all()
            print(f"Found {len(dropdown_triggers)} dropdown trigger buttons")
            
            if len(dropdown_triggers) > 0:
                print(f"🎯 Clicking first dropdown trigger...")
                first_trigger = dropdown_triggers[0]
                
                # Click the dropdown trigger
                first_trigger.click()
                time.sleep(2)  # Wait for dropdown
                print("✅ Dropdown trigger clicked!")
                
                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "targeted_dropdown_open.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                print(f"📸 Dropdown opened: {screenshot_path}")
                
                # Look for dropdown menu items
                print(f"\n📋 Analyzing dropdown menu...")
                
                # Wait a moment for dropdown to fully appear
                time.sleep(1)
                
                # Look for dropdown menu items using various selectors
                dropdown_items = []
                
                # Ant Design dropdown menu items
                ant_dropdown_items = page.locator('.ant-dropdown-menu-item:visible').all()
                for item in ant_dropdown_items:
                    text = item.inner_text().strip()
                    if text:
                        dropdown_items.append(('ant-dropdown-menu-item', text, item))
                        print(f"  📝 [Ant Dropdown] {text}")
                
                # Alternative selectors for menu items
                if len(dropdown_items) == 0:
                    print("  🔍 No ant-dropdown-menu-item found, trying alternatives...")
                    
                    alternative_selectors = [
                        'li:visible[role="menuitem"]',
                        '.ant-menu-item:visible',
                        'li:visible',
                        '[role="menuitem"]:visible'
                    ]
                    
                    for selector in alternative_selectors:
                        items = page.locator(selector).all()
                        print(f"    {selector}: found {len(items)} items")
                        for item in items:
                            text = item.inner_text().strip()
                            if text and not any(text in existing[1] for existing in dropdown_items):
                                dropdown_items.append((selector, text, item))
                                print(f"  📝 [{selector}] {text}")
                
                print(f"\n📋 Total dropdown items found: {len(dropdown_items)}")
                
                # Look specifically for pause option
                pause_items = []
                for selector_type, text, element in dropdown_items:
                    if 'pause' in text.lower():
                        pause_items.append((selector_type, text, element))
                        print(f"🎯 FOUND PAUSE OPTION: {text}")
                
                if len(pause_items) > 0:
                    print(f"\n🎯 CLICKING PAUSE OPTION...")
                    selector_type, pause_text, pause_element = pause_items[0]
                    print(f"Clicking: '{pause_text}' (found via {selector_type})")
                    
                    # Click the pause option
                    pause_element.click()
                    print("✅ Pause option clicked!")
                    
                    time.sleep(4)  # Wait for pause action to complete
                    
                    screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "targeted_after_pause.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"📸 After pause action: {screenshot_path}")
                    
                    # Check for results
                    print(f"\n🔍 CHECKING FOR PAUSE RESULTS...")
                    
                    # Look for success messages/notifications
                    success_found = False
                    notification_selectors = [
                        '.ant-notification:visible',
                        '.ant-message:visible', 
                        '.toast:visible',
                        '.alert:visible',
                        '[class*="success"]:visible',
                        '[class*="notification"]:visible'
                    ]
                    
                    for selector in notification_selectors:
                        elements = page.locator(selector).all()
                        for elem in elements:
                            text = elem.inner_text().strip()
                            if text:
                                print(f"✅ SUCCESS MESSAGE [{selector}]: {text}")
                                success_found = True
                    
                    # Check console logs
                    recent_console = [log for log in console_logs 
                                    if 'pause' in log['text'].lower() or 'container' in log['text'].lower()]
                    if recent_console:
                        print(f"📝 Console messages about pause/container ({len(recent_console)}):")
                        for log in recent_console[-5:]:
                            print(f"  [{log['type']}] {log['text']}")
                    
                    # Check network requests
                    pause_requests = [log for log in network_logs 
                                    if ('pause' in log['url'].lower() or 
                                        'container' in log['url'].lower()) and 
                                       log['type'] == 'request']
                    if pause_requests:
                        print(f"🌐 Network requests for pause/container ({len(pause_requests)}):")
                        for log in pause_requests[-5:]:
                            print(f"  {log['method']} {log['url']}")
                    
                    # Check for API responses
                    pause_responses = [log for log in network_logs 
                                     if ('pause' in log['url'].lower() or 
                                         'container' in log['url'].lower()) and 
                                        log['type'] == 'response']
                    if pause_responses:
                        print(f"📡 API responses for pause/container ({len(pause_responses)}):")
                        for log in pause_responses[-5:]:
                            print(f"  {log['url']} -> Status: {log['status']}")
                    
                    # Look for visual changes (status indicators, etc.)
                    print(f"\n👀 LOOKING FOR VISUAL CHANGES...")
                    status_elements = page.locator('[class*="status"], [class*="state"], [class*="paused"], [class*="running"]').all()
                    visual_changes = []
                    for elem in status_elements:
                        if elem.is_visible():
                            text = elem.inner_text().strip()
                            classes = elem.get_attribute('class') or ''
                            if text or 'paused' in classes.lower() or 'status' in classes.lower():
                                visual_changes.append(f"Text: '{text}', Classes: {classes}")
                    
                    if visual_changes:
                        print(f"Visual status indicators found ({len(visual_changes)}):")
                        for change in visual_changes[:5]:
                            print(f"  {change}")
                    else:
                        print("No obvious visual status changes detected")
                    
                    if not success_found and not recent_console and not pause_requests:
                        print("⚠️  No immediate success indicators found - pause action may be queued or async")
                    else:
                        print("✅ PAUSE ACTION APPEARS TO HAVE BEEN PROCESSED!")
                        
                else:
                    print("❌ No pause option found in dropdown menu")
                    if dropdown_items:
                        print(f"Available options were:")
                        for selector_type, text, element in dropdown_items:
                            print(f"  - {text}")
                        
                        # Try the first option to see what happens
                        if len(dropdown_items) > 0:
                            print(f"\n🎯 Trying first available option: '{dropdown_items[0][1]}'")
                            try:
                                dropdown_items[0][2].click()
                                time.sleep(3)
                                
                                screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "targeted_first_option.png"
                                page.screenshot(path=str(screenshot_path), full_page=True)
                                print(f"📸 After first option: {screenshot_path}")
                            except Exception as e:
                                print(f"❌ Error clicking first option: {e}")
                    else:
                        print("No dropdown items found at all")
                        
            else:
                print("❌ No dropdown trigger buttons found")
            
            # Final screenshot
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "targeted_final.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"📸 Final state: {screenshot_path}")
            
            # Save logs
            logs_path = Path(__file__).parent / "artifacts" / "logs" / "targeted_test_logs.json"
            logs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(logs_path, 'w') as f:
                json.dump({
                    'network_logs': network_logs,
                    'console_logs': console_logs
                }, f, indent=2)
            print(f"💾 Complete logs saved: {logs_path}")
            
            print(f"\n🎯 TARGETED TEST COMPLETED!")
            time.sleep(8)
            
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            if 'page' in locals():
                error_screenshot = Path(__file__).parent / "artifacts" / "screenshots" / "targeted_error.png"
                error_screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(error_screenshot), full_page=True)
                print(f"📸 Error screenshot: {error_screenshot}")
            raise
            
        finally:
            if browser:
                browser.close()
            print("👋 Browser closed.")


if __name__ == "__main__":
    run()