#!/usr/bin/env python3
"""
User Deactivation UI Explorer
Interactive exploration of the user deactivation functionality
"""

import time
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    """Explore the user deactivation functionality step by step"""
    
    with sync_playwright() as p:
        # Launch browser with visible UI
        browser = p.chromium.launch(headless=False, slow_mo=1000)
        context = browser.new_context(
            viewport={'width': 1440, 'height': 900}
        )
        page = context.new_page()
        
        # Create screenshot directory
        screenshots_dir = Path("artifacts/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            print("🚀 Starting User Deactivation UI Exploration")
            
            # Step 1: Navigate to console
            print("1. Navigating to console...")
            page.goto("http://localhost:7322/console")
            page.wait_for_load_state("domcontentloaded")
            page.screenshot(path=str(screenshots_dir / "01_initial_load.png"))
            
            # Step 2: Handle login if needed
            print("2. Checking if login is needed...")
            current_url = page.url
            if '/login' in current_url or current_url.endswith('/console/'):
                print("   Logging in...")
                
                # Try different login selectors
                email_selectors = [
                    '[data-testid="login-email-input"]',
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[placeholder*="email" i]'
                ]
                
                email_input = None
                for selector in email_selectors:
                    try:
                        email_input = page.locator(selector).first
                        if email_input.is_visible():
                            print(f"   Found email input with selector: {selector}")
                            break
                    except:
                        continue
                
                if email_input:
                    email_input.fill("admin@rediacc.io")
                    
                    # Find password input
                    password_selectors = [
                        '[data-testid="login-password-input"]',
                        'input[type="password"]',
                        'input[name="password"]'
                    ]
                    
                    password_input = None
                    for selector in password_selectors:
                        try:
                            password_input = page.locator(selector).first
                            if password_input.is_visible():
                                print(f"   Found password input with selector: {selector}")
                                break
                        except:
                            continue
                    
                    if password_input:
                        password_input.fill("admin")
                        
                        # Find submit button
                        submit_selectors = [
                            '[data-testid="login-submit-button"]',
                            'button[type="submit"]',
                            'button:has-text("Sign In")',
                            'button:has-text("Login")'
                        ]
                        
                        for selector in submit_selectors:
                            try:
                                submit_button = page.locator(selector).first
                                if submit_button.is_visible():
                                    print(f"   Found submit button with selector: {selector}")
                                    submit_button.click()
                                    break
                            except:
                                continue
                        
                        # Wait for dashboard
                        try:
                            page.wait_for_url("**/console/dashboard", timeout=10000)
                            print("   ✅ Login successful!")
                        except:
                            print("   ⚠️ Login might have failed or different redirect")
                            
                page.screenshot(path=str(screenshots_dir / "02_after_login.png"))
            
            # Step 3: Navigate to System page
            print("3. Navigating to System page...")
            
            # Try different system navigation methods
            system_selectors = [
                '[data-testid="main-nav-system"]',
                'nav a:has-text("System")',
                'a[href*="/system"]',
                '[data-testid*="system"]',
                '.ant-menu-item:has-text("System")'
            ]
            
            system_clicked = False
            for selector in system_selectors:
                try:
                    system_link = page.locator(selector).first
                    if system_link.is_visible():
                        print(f"   Found System link with selector: {selector}")
                        system_link.click()
                        system_clicked = True
                        break
                except:
                    continue
            
            if not system_clicked:
                print("   ⚠️ Could not find System navigation link")
                
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(screenshots_dir / "03_system_page.png"))
            
            # Step 4: Explore the Users tab
            print("4. Exploring Users tab...")
            
            # Check if we're on Users tab by default
            users_tab_selectors = [
                '[data-testid="system-users-tab"]',
                '.ant-tabs-tab:has-text("Users")',
                'div[role="tab"]:has-text("Users")',
                '[data-node-key="users"]'
            ]
            
            users_tab_found = False
            for selector in users_tab_selectors:
                try:
                    users_tab = page.locator(selector).first
                    if users_tab.is_visible():
                        print(f"   Found Users tab with selector: {selector}")
                        users_tab.click()
                        users_tab_found = True
                        break
                except:
                    continue
            
            if not users_tab_found:
                print("   ⚠️ Could not find Users tab, might be default")
                
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(screenshots_dir / "04_users_tab.png"))
            
            # Step 5: Explore user table and find deactivation buttons
            print("5. Exploring user table...")
            
            # Look for the users table
            table_selectors = [
                '.ant-table-tbody',
                'table tbody',
                '[data-testid="users-table"] tbody'
            ]
            
            table_found = False
            for selector in table_selectors:
                try:
                    table = page.locator(selector).first
                    if table.is_visible():
                        print(f"   Found table with selector: {selector}")
                        table_found = True
                        
                        # Get all rows
                        rows = table.locator('tr').all()
                        print(f"   Found {len(rows)} rows in table")
                        
                        # Examine each row for user data and buttons
                        for i, row in enumerate(rows[:5]):  # Limit to first 5 rows
                            try:
                                row_text = row.text_content()
                                print(f"   Row {i+1}: {row_text[:100]}...")
                                
                                # Look for action buttons in this row
                                button_selectors = [
                                    'button',
                                    'button:has-text("Deactivate")',
                                    'button:has-text("Activate")',
                                    '[data-testid*="deactivate"]',
                                    '[data-testid*="activate"]'
                                ]
                                
                                for btn_selector in button_selectors:
                                    try:
                                        buttons = row.locator(btn_selector).all()
                                        for j, button in enumerate(buttons):
                                            if button.is_visible():
                                                button_text = button.text_content()
                                                print(f"     Button {j+1}: '{button_text}' - selector: {btn_selector}")
                                                
                                                # Try to get data-testid if available
                                                try:
                                                    testid = button.get_attribute('data-testid')
                                                    if testid:
                                                        print(f"       data-testid: {testid}")
                                                except:
                                                    pass
                                    except:
                                        continue
                                        
                            except Exception as e:
                                print(f"   Error examining row {i+1}: {e}")
                        
                        break
                except:
                    continue
            
            if not table_found:
                print("   ⚠️ Could not find users table")
            
            page.screenshot(path=str(screenshots_dir / "05_table_exploration.png"))
            
            # Step 6: Try to find and click a deactivate button
            print("6. Looking for deactivate button...")
            
            deactivate_selectors = [
                'button:has-text("Deactivate")',
                '[data-testid*="deactivate-button"]',
                '[data-testid*="user-deactivate"]',
                'button[title*="deactivate"]',
                'button[title*="Deactivate"]',
                '.ant-btn:has-text("Deactivate")'
            ]
            
            deactivate_found = False
            for selector in deactivate_selectors:
                try:
                    deactivate_buttons = page.locator(selector).all()
                    if len(deactivate_buttons) > 0:
                        for i, button in enumerate(deactivate_buttons):
                            if button.is_visible():
                                print(f"   Found deactivate button {i+1} with selector: {selector}")
                                
                                # Get button attributes
                                try:
                                    testid = button.get_attribute('data-testid')
                                    title = button.get_attribute('title')
                                    class_attr = button.get_attribute('class')
                                    print(f"     data-testid: {testid}")
                                    print(f"     title: {title}")
                                    print(f"     class: {class_attr}")
                                except:
                                    pass
                                
                                # Click the first visible deactivate button
                                if not deactivate_found:
                                    print(f"     Clicking deactivate button...")
                                    button.click()
                                    deactivate_found = True
                                    time.sleep(1)  # Wait for dialog
                                    break
                        
                        if deactivate_found:
                            break
                except:
                    continue
            
            if deactivate_found:
                page.screenshot(path=str(screenshots_dir / "06_deactivate_clicked.png"))
                
                # Step 7: Explore confirmation dialog
                print("7. Exploring confirmation dialog...")
                
                dialog_selectors = [
                    '.ant-modal',
                    '[role="dialog"]',
                    '.ant-confirm',
                    '.ant-popconfirm'
                ]
                
                dialog_found = False
                for selector in dialog_selectors:
                    try:
                        dialog = page.locator(selector).first
                        if dialog.is_visible():
                            print(f"   Found dialog with selector: {selector}")
                            dialog_found = True
                            
                            # Get dialog content
                            dialog_text = dialog.text_content()
                            print(f"   Dialog content: {dialog_text}")
                            
                            # Look for confirmation buttons
                            confirm_selectors = [
                                'button:has-text("Yes")',
                                'button:has-text("OK")',
                                'button:has-text("Confirm")',
                                'button:has-text("Deactivate")',
                                '[data-testid="confirm-yes-button"]',
                                '.ant-btn-primary',
                                '.ant-btn-dangerous'
                            ]
                            
                            for conf_selector in confirm_selectors:
                                try:
                                    confirm_buttons = dialog.locator(conf_selector).all()
                                    for button in confirm_buttons:
                                        if button.is_visible():
                                            button_text = button.text_content()
                                            print(f"     Confirm button: '{button_text}' - selector: {conf_selector}")
                                            
                                            # Get button attributes
                                            try:
                                                testid = button.get_attribute('data-testid')
                                                class_attr = button.get_attribute('class')
                                                if testid:
                                                    print(f"       data-testid: {testid}")
                                                if class_attr:
                                                    print(f"       class: {class_attr}")
                                            except:
                                                pass
                                except:
                                    continue
                            
                            break
                    except:
                        continue
                
                if not dialog_found:
                    print("   ⚠️ No confirmation dialog found")
                
                page.screenshot(path=str(screenshots_dir / "07_dialog_exploration.png"))
                
                # Try to confirm if dialog exists
                if dialog_found:
                    print("8. Attempting to confirm deactivation...")
                    
                    confirm_selectors = [
                        'button:has-text("Yes")',
                        'button:has-text("OK")',
                        'button:has-text("Confirm")',
                        '[data-testid="confirm-yes-button"]'
                    ]
                    
                    confirmed = False
                    for selector in confirm_selectors:
                        try:
                            confirm_button = page.locator(selector).first
                            if confirm_button.is_visible():
                                print(f"   Confirming with selector: {selector}")
                                confirm_button.click()
                                confirmed = True
                                time.sleep(2)  # Wait for action to complete
                                break
                        except:
                            continue
                    
                    if confirmed:
                        page.screenshot(path=str(screenshots_dir / "08_after_confirmation.png"))
                        
                        # Look for success messages
                        print("9. Looking for success messages...")
                        
                        message_selectors = [
                            '.ant-message',
                            '.ant-notification',
                            '[class*="success"]',
                            '[class*="message"]',
                            '.ant-alert-success'
                        ]
                        
                        for selector in message_selectors:
                            try:
                                messages = page.locator(selector).all()
                                for message in messages:
                                    if message.is_visible():
                                        message_text = message.text_content()
                                        print(f"     Success message: '{message_text}' - selector: {selector}")
                            except:
                                continue
                                
                    else:
                        print("   ⚠️ Could not confirm deactivation")
                        
            else:
                print("   ⚠️ No deactivate button found")
                
                # Look for activate buttons instead (user might be deactivated)
                print("   Looking for activate buttons...")
                
                activate_selectors = [
                    'button:has-text("Activate")',
                    '[data-testid*="activate-button"]',
                    '[data-testid*="user-activate"]',
                    'button[title*="activate"]',
                    'button[title*="Activate"]'
                ]
                
                for selector in activate_selectors:
                    try:
                        activate_buttons = page.locator(selector).all()
                        for i, button in enumerate(activate_buttons):
                            if button.is_visible():
                                print(f"     Found activate button {i+1} with selector: {selector}")
                                # Get attributes
                                try:
                                    testid = button.get_attribute('data-testid')
                                    if testid:
                                        print(f"       data-testid: {testid}")
                                except:
                                    pass
                    except:
                        continue
            
            # Final screenshot
            page.screenshot(path=str(screenshots_dir / "09_final_state.png"))
            
            print("\n✅ Exploration completed!")
            print(f"Screenshots saved to: {screenshots_dir}")
            
            # Keep browser open for manual inspection
            input("Press Enter to close browser...")
            
        except Exception as e:
            print(f"❌ Error during exploration: {e}")
            page.screenshot(path=str(screenshots_dir / "error_exploration.png"))
            
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()