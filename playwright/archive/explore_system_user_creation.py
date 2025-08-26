#!/usr/bin/env python3
"""
System User Creation Explorer
Explores the System page to discover selectors and functionality for user creation
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

# Load config
config_path = Path("/home/anl/monorepo/console/playwright/config.json")
with open(config_path) as f:
    config = json.load(f)

def explore_system_user_creation():
    """Explore the System page and user creation functionality"""
    with sync_playwright() as p:
        # Launch browser with non-headless mode for visual debugging
        browser = p.chromium.launch(
            headless=False,
            slow_mo=1000  # Slow down for observation
        )
        
        context = browser.new_context(
            viewport={'width': 1440, 'height': 900}
        )
        
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(10000)
        
        try:
            print("1. Navigating to console...")
            page.goto(config['baseUrl'] + "/console")
            
            # Take initial screenshot
            page.screenshot(path="explore_01_initial.png", full_page=True)
            print("   Screenshot: explore_01_initial.png")
            
            # Check if we need to login
            if '/login' in page.url or 'signin' in page.url:
                print("2. Logging in...")
                
                # Fill login form
                email_input = page.locator('input[type="email"], input[placeholder*="email" i]').first
                email_input.fill(config['login']['credentials']['email'])
                
                password_input = page.locator('input[type="password"]').first
                password_input.fill(config['login']['credentials']['password'])
                
                # Submit form
                submit_button = page.locator('button[type="submit"], button:has-text("Sign In")').first
                submit_button.click()
                
                # Wait for dashboard
                page.wait_for_url("**/console/dashboard", timeout=10000)
                print("   Login successful!")
                
                # Take post-login screenshot
                page.screenshot(path="explore_02_dashboard.png", full_page=True)
                print("   Screenshot: explore_02_dashboard.png")
            
            print("3. Navigating to System page...")
            
            # Try to find and click System navigation
            system_nav_selectors = [
                '[data-testid="main-nav-system"]',
                'nav a:has-text("System")',
                'a[href*="system"]',
                '.ant-menu-item:has-text("System")'
            ]
            
            system_found = False
            for selector in system_nav_selectors:
                try:
                    system_link = page.locator(selector).first
                    if system_link.is_visible():
                        print(f"   Found System link with selector: {selector}")
                        system_link.click()
                        system_found = True
                        break
                except:
                    continue
            
            if not system_found:
                print("   System navigation not found, exploring available navigation...")
                nav_items = page.locator('nav a, .ant-menu-item').all()
                print(f"   Available navigation items: {len(nav_items)}")
                for i, item in enumerate(nav_items):
                    try:
                        text = item.inner_text()
                        print(f"     {i}: {text}")
                    except:
                        print(f"     {i}: [unable to get text]")
                
                # Try alternative ways to navigate
                try:
                    page.goto(config['baseUrl'] + "/console/system")
                    print("   Navigated directly to /console/system")
                except:
                    print("   Direct navigation failed")
            
            # Wait for page to load
            page.wait_for_load_state("networkidle", timeout=5000)
            
            # Take System page screenshot
            page.screenshot(path="explore_03_system_page.png", full_page=True)
            print("   Screenshot: explore_03_system_page.png")
            
            print("4. Exploring System page structure...")
            
            # Get page title and URL
            page_title = page.title()
            current_url = page.url
            print(f"   Page title: {page_title}")
            print(f"   Current URL: {current_url}")
            
            # Look for tabs or sections
            tabs = page.locator('.ant-tabs-tab, [role="tab"], .tab').all()
            print(f"   Found {len(tabs)} tabs/sections:")
            for i, tab in enumerate(tabs):
                try:
                    text = tab.inner_text()
                    test_id = tab.get_attribute('data-testid') or 'none'
                    print(f"     Tab {i}: {text} (testid: {test_id})")
                except:
                    print(f"     Tab {i}: [unable to get text]")
            
            # Look for Create User button or similar
            print("5. Looking for Create User functionality...")
            create_user_selectors = [
                '[data-testid*="create-user"]',
                '[data-testid*="system-create-user"]',
                'button:has-text("Create User")',
                'button:has-text("Add User")',
                'button:has-text("New User")',
                'button[title*="user" i]',
                '.ant-btn:has-text("Create")',
                '.ant-btn:has-text("Add")',
                '[aria-label*="create" i]',
                '[aria-label*="add" i]'
            ]
            
            create_button_found = False
            for selector in create_user_selectors:
                try:
                    buttons = page.locator(selector).all()
                    for button in buttons:
                        if button.is_visible():
                            text = button.inner_text()
                            test_id = button.get_attribute('data-testid') or 'none'
                            aria_label = button.get_attribute('aria-label') or 'none'
                            title = button.get_attribute('title') or 'none'
                            print(f"   Found button with selector '{selector}': text='{text}', testid='{test_id}', aria-label='{aria_label}', title='{title}'")
                            create_button_found = True
                except:
                    continue
            
            if not create_button_found:
                print("   No Create User button found with standard selectors")
                # Look for any buttons on the page
                all_buttons = page.locator('button').all()
                print(f"   Found {len(all_buttons)} buttons total:")
                for i, button in enumerate(all_buttons):
                    try:
                        if button.is_visible():
                            text = button.inner_text()
                            test_id = button.get_attribute('data-testid') or 'none'
                            classes = button.get_attribute('class') or 'none'
                            print(f"     Button {i}: '{text}' (testid: {test_id}, classes: {classes})")
                    except:
                        print(f"     Button {i}: [unable to get details]")
            
            # Try to click on Users tab if it exists
            users_tab_selectors = [
                '.ant-tabs-tab:has-text("Users")',
                '[role="tab"]:has-text("Users")',
                '.tab:has-text("Users")',
                '[data-testid*="users"]'
            ]
            
            users_tab_found = False
            for selector in users_tab_selectors:
                try:
                    tab = page.locator(selector).first
                    if tab.is_visible():
                        print(f"   Found Users tab with selector: {selector}")
                        tab.click()
                        users_tab_found = True
                        
                        # Wait for tab content to load
                        page.wait_for_timeout(1000)
                        
                        # Take screenshot after clicking Users tab
                        page.screenshot(path="explore_04_users_tab.png", full_page=True)
                        print("   Screenshot: explore_04_users_tab.png")
                        
                        # Re-look for Create User button
                        print("6. Re-examining Create User functionality after Users tab...")
                        for selector in create_user_selectors:
                            try:
                                buttons = page.locator(selector).all()
                                for button in buttons:
                                    if button.is_visible():
                                        text = button.inner_text()
                                        test_id = button.get_attribute('data-testid') or 'none'
                                        print(f"     Found Create button: '{text}' (testid: {test_id})")
                                        
                                        # Try to click it
                                        print(f"   Clicking Create User button: {text}")
                                        button.click()
                                        
                                        # Wait for modal/dialog to appear
                                        page.wait_for_timeout(2000)
                                        
                                        # Take screenshot of modal
                                        page.screenshot(path="explore_05_create_user_modal.png", full_page=True)
                                        print("   Screenshot: explore_05_create_user_modal.png")
                                        
                                        # Explore modal content
                                        print("7. Exploring Create User modal/dialog...")
                                        
                                        # Look for modal container
                                        modal_selectors = [
                                            '.ant-modal',
                                            '[role="dialog"]',
                                            '.modal',
                                            '.dialog'
                                        ]
                                        
                                        modal_found = False
                                        for modal_selector in modal_selectors:
                                            try:
                                                modal = page.locator(modal_selector).first
                                                if modal.is_visible():
                                                    print(f"   Found modal with selector: {modal_selector}")
                                                    modal_found = True
                                                    
                                                    # Look for input fields in modal
                                                    inputs = modal.locator('input').all()
                                                    print(f"   Found {len(inputs)} input fields in modal:")
                                                    for i, inp in enumerate(inputs):
                                                        try:
                                                            input_type = inp.get_attribute('type') or 'text'
                                                            placeholder = inp.get_attribute('placeholder') or 'none'
                                                            name = inp.get_attribute('name') or 'none'
                                                            test_id = inp.get_attribute('data-testid') or 'none'
                                                            print(f"     Input {i}: type='{input_type}', placeholder='{placeholder}', name='{name}', testid='{test_id}'")
                                                        except:
                                                            print(f"     Input {i}: [unable to get details]")
                                                    
                                                    # Look for buttons in modal
                                                    modal_buttons = modal.locator('button').all()
                                                    print(f"   Found {len(modal_buttons)} buttons in modal:")
                                                    for i, btn in enumerate(modal_buttons):
                                                        try:
                                                            text = btn.inner_text()
                                                            test_id = btn.get_attribute('data-testid') or 'none'
                                                            btn_type = btn.get_attribute('type') or 'none'
                                                            classes = btn.get_attribute('class') or 'none'
                                                            print(f"     Button {i}: '{text}' (testid: {test_id}, type: {btn_type}, classes: {classes})")
                                                        except:
                                                            print(f"     Button {i}: [unable to get details]")
                                                    
                                                    break
                                            except:
                                                continue
                                        
                                        if not modal_found:
                                            print("   No modal found, might be inline form")
                                        
                                        # Don't fill the form, just explore
                                        return
                                        
                            except Exception as e:
                                print(f"     Error with selector {selector}: {e}")
                                continue
                        break
                except:
                    continue
            
            if not users_tab_found:
                print("   No Users tab found")
            
            print("\n8. Final page exploration...")
            # Get all elements with data-testid attributes
            testid_elements = page.locator('[data-testid]').all()
            print(f"   Found {len(testid_elements)} elements with data-testid:")
            for i, elem in enumerate(testid_elements[:20]):  # Limit to first 20
                try:
                    test_id = elem.get_attribute('data-testid')
                    tag = elem.evaluate('el => el.tagName.toLowerCase()')
                    text = elem.inner_text()[:50] if elem.inner_text() else '[no text]'
                    print(f"     {i}: {tag}[data-testid='{test_id}'] = '{text}'")
                except:
                    print(f"     {i}: [unable to get details]")
            
            # Take final screenshot
            page.screenshot(path="explore_06_final.png", full_page=True)
            print("   Screenshot: explore_06_final.png")
            
            print("\nExploration completed! Check screenshots for visual reference.")
            
        except Exception as e:
            print(f"Error during exploration: {e}")
            page.screenshot(path="explore_error.png", full_page=True)
            print("Error screenshot saved as: explore_error.png")
            
        finally:
            # Keep browser open for 10 seconds to allow manual inspection
            print("Browser will close in 10 seconds...")
            time.sleep(10)
            browser.close()

if __name__ == "__main__":
    explore_system_user_creation()