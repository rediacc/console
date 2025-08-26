#!/usr/bin/env python3
"""
Bridge Edit Explorer - Explore bridges tab and available bridges
"""

import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    """Explore bridges tab"""
    browser = None
    context = None
    
    try:
        print("Starting Bridge Edit Explorer...")
        
        # Launch browser
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Navigate to console
        print("1. Navigating to console...")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Login
        current_url = page.url
        print(f"2. Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            print("3. Logging in...")
            
            # Find email input
            email_input = page.locator('input[type="email"]').first
            email_input.fill("admin@rediacc.io")
            
            # Find password input
            password_input = page.locator('input[type="password"]').first
            password_input.fill("admin")
            
            # Find and click submit button
            submit_button = page.locator('button[type="submit"]').first
            submit_button.click()
            
            # Wait for dashboard
            page.wait_for_url("**/console/dashboard", timeout=10000)
            print("   Login successful!")
        
        # Navigate to System
        print("4. Navigating to System...")
        system_link = page.get_by_text("System")
        system_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # Switch to Expert mode
        print("5. Switching to Expert mode...")
        try:
            expert_element = page.locator('label:has-text("Expert")').first
            if expert_element.is_visible():
                expert_element.click()
                time.sleep(1)
                print("   Switched to Expert mode")
        except:
            print("   Could not switch to Expert mode")
        
        # Take screenshot of system page with all tabs
        screenshot_path = Path(__file__).parent / "system_page_full.png"
        page.screenshot(path=str(screenshot_path))
        print(f"6. System page screenshot: {screenshot_path}")
        
        # Look for all available tabs
        print("7. Looking for available tabs...")
        tabs = page.locator('[role="tab"], .ant-tabs-tab, button:has-text("Users"), button:has-text("Teams"), button:has-text("Permissions"), button:has-text("User Sessions"), text=Bridges, text=Regions').all()
        tab_names = []
        for i, tab in enumerate(tabs):
            try:
                text = tab.inner_text()
                tab_names.append(text)
                print(f"   Tab {i+1}: {text}")
            except:
                print(f"   Tab {i+1}: Could not get text")
        
        # Try to click on different elements that might be Bridges
        print("8. Looking for Bridges tab or content...")
        bridges_found = False
        
        # Multiple strategies to find bridges
        bridges_selectors = [
            'button:has-text("Bridges")',
            'a:has-text("Bridges")',
            '[role="tab"]:has-text("Bridges")',
            '.ant-tabs-tab:has-text("Bridges")',
            'text=Bridges',
            '*[class*="bridge"]',
            '*[data-testid*="bridge"]'
        ]
        
        for selector in bridges_selectors:
            try:
                bridges_element = page.locator(selector).first
                if bridges_element.is_visible():
                    print(f"   Found Bridges element with selector: {selector}")
                    bridges_element.click()
                    time.sleep(1)
                    bridges_found = True
                    break
            except:
                continue
        
        if not bridges_found:
            # Try scrolling down or looking for more tabs
            print("9. Bridges not found in visible tabs, exploring further...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            
            # Try to find any element containing "bridge"
            all_elements = page.locator('*:has-text("bridge")').all()
            print(f"   Found {len(all_elements)} elements containing 'bridge'")
            for i, element in enumerate(all_elements):
                try:
                    text = element.inner_text()
                    if text and "bridge" in text.lower():
                        print(f"     Element {i+1}: {text}")
                except:
                    pass
        else:
            print("9. Bridges tab found and clicked")
        
        # Take screenshot after attempting to find bridges
        screenshot_after = Path(__file__).parent / "system_page_after_bridges_search.png"
        page.screenshot(path=str(screenshot_after))
        print(f"10. Screenshot after bridges search: {screenshot_after}")
        
        # Look for any tables or lists that might contain bridges
        print("11. Looking for tables or lists...")
        tables = page.locator('table, .ant-table, [role="table"], .ant-list').all()
        print(f"   Found {len(tables)} potential table/list elements")
        
        for i, table in enumerate(tables):
            try:
                # Take screenshot of each table
                table_screenshot = Path(__file__).parent / f"table_{i+1}.png"
                table.screenshot(path=str(table_screenshot))
                print(f"   Table {i+1} screenshot: {table_screenshot}")
                
                # Try to get table content
                rows = table.locator('tr, .ant-table-row, .ant-list-item').all()
                print(f"   Table {i+1} has {len(rows)} rows/items")
                
                for j, row in enumerate(rows[:5]):  # First 5 rows only
                    try:
                        row_text = row.inner_text()
                        if row_text:
                            print(f"     Row {j+1}: {row_text[:100]}...")  # First 100 chars
                    except:
                        pass
            except:
                print(f"   Could not capture table {i+1}")
        
        # Look for any edit buttons
        print("12. Looking for edit buttons...")
        edit_buttons = page.locator('button:has-text("Edit"), button[title*="edit"], button[title*="Edit"], [data-testid*="edit"]').all()
        print(f"   Found {len(edit_buttons)} potential edit buttons")
        
        for i, button in enumerate(edit_buttons):
            try:
                button_text = button.inner_text() or button.get_attribute('title') or button.get_attribute('data-testid')
                print(f"   Edit button {i+1}: {button_text}")
            except:
                print(f"   Edit button {i+1}: Could not get text")
        
        print("\nExploration completed!")
        
        # Keep browser open for inspection
        time.sleep(5)
        
    except Exception as e:
        print(f"\nError during exploration: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            error_screenshot = Path(__file__).parent / "error_bridge_exploration.png"
            page.screenshot(path=str(error_screenshot))
            print(f"Error screenshot: {error_screenshot}")
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
        print("\nExploration interrupted by user")
    except Exception as e:
        print(f"\nExploration failed: {str(e)}")


if __name__ == "__main__":
    main()