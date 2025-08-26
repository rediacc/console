#!/usr/bin/env python3
"""
System User Deactivate Test - Smart Version
Tests the user deactivation functionality in Rediacc console
Uses config.json for all settings and credentials
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class UserDeactivationTest:
    """Smart user deactivation test with configuration support"""
    
    def __init__(self, config_path="config.json"):
        """Initialize test with configuration"""
        self.config = self.load_config(config_path)
        self.browser = None
        self.context = None
        self.page = None
        self.target_user = None
        
    def load_config(self, config_path):
        """Load configuration from JSON file"""
        config_file = Path(__file__).parent / config_path
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Add systemDeactivateUser configuration if not exists
        if 'systemDeactivateUser' not in config:
            config['systemDeactivateUser'] = {
                "ui": {
                    "systemNavTestId": "main-nav-system",
                    "usersTabSelector": ".ant-tabs-tab:has-text('Users')",
                    "deactivateButtonPrefix": "system-user-deactivate-button-",
                    "activateButtonPrefix": "system-user-activate-button-",
                    "confirmDialogSelector": ".ant-popconfirm",
                    "confirmYesButton": ".ant-popconfirm button.ant-btn-dangerous:has-text('Yes')",
                    "confirmNoButton": ".ant-popconfirm button:has-text('No')",
                    "usersTableSelector": "table.ant-table",
                    "statusActiveTag": ".ant-tag-green",
                    "statusInactiveTag": ".ant-tag-default",
                    "userRowSelector": "tr.ant-table-row"
                },
                "testData": {
                    "targetUserEmail": null,
                    "preferNonAdminUsers": true,
                    "skipProtectedUsers": ["admin@rediacc.io", "bridge"],
                    "testMode": "first_available"
                },
                "validation": {
                    "successIndicators": [
                        "User deactivated successfully",
                        "User '.*' deactivated successfully",
                        "Successfully deactivated user",
                        "User status updated"
                    ],
                    "errorMessages": [
                        "Cannot deactivate admin user",
                        "User not found",
                        "Deactivation failed",
                        "Protected user"
                    ],
                    "notificationSelectors": [
                        ".ant-message",
                        ".ant-notification",
                        "[role='alert']"
                    ],
                    "statusChangeVerification": true
                },
                "timeouts": {
                    "navigation": 10000,
                    "element": 5000,
                    "confirmDialog": 3000,
                    "deactivation": 5000,
                    "statusUpdate": 3000,
                    "validation": 5000
                }
            }
        
        return config
    
    def setup_browser(self, playwright: Playwright):
        """Setup browser with configuration settings"""
        browser_config = self.config.get('browser', {})
        
        self.browser = playwright.chromium.launch(
            headless=browser_config.get('headless', False),
            slow_mo=browser_config.get('slowMo', 0)
        )
        
        viewport = browser_config.get('viewport', {'width': 1280, 'height': 720})
        self.context = self.browser.new_context(viewport=viewport)
        self.page = self.context.new_page()
        
        # Set default timeout
        default_timeout = self.config.get('timeouts', {}).get('pageLoad', 30000)
        self.page.set_default_timeout(default_timeout)
        
        print(f"Browser setup complete (headless: {browser_config.get('headless', False)})")
    
    def login(self):
        """Login to the application using config credentials"""
        print("\n1. Navigating to login page...")
        
        base_url = self.config.get('baseUrl', 'http://localhost:7322')
        self.page.goto(f"{base_url}/console")
        
        # Wait for login form
        login_config = self.config.get('login', {})
        credentials = login_config.get('credentials', {})
        timeouts = login_config.get('timeouts', {})
        
        print("2. Waiting for login form...")
        
        # Smart wait for email input
        email_selectors = [
            f'[data-testid="login-email-input"]',
            'input[type="email"]',
            'input[placeholder*="email" i]'
        ]
        
        email_input = None
        for selector in email_selectors:
            try:
                email_input = self.page.locator(selector).first
                if email_input.is_visible(timeout=1000):
                    break
            except:
                continue
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        # Fill credentials
        print(f"3. Logging in as {credentials.get('email')}...")
        email_input.fill(credentials.get('email', 'admin@rediacc.io'))
        
        # Password input
        password_selectors = [
            f'[data-testid="login-password-input"]',
            'input[type="password"]'
        ]
        
        password_input = None
        for selector in password_selectors:
            try:
                password_input = self.page.locator(selector).first
                if password_input.is_visible(timeout=1000):
                    break
            except:
                continue
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        password_input.fill(credentials.get('password', 'admin'))
        
        # Submit
        submit_selectors = [
            f'[data-testid="login-submit-button"]',
            'button[type="submit"]',
            'button:has-text("Sign In")'
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = self.page.locator(selector).first
                if submit_button.is_visible(timeout=1000):
                    break
            except:
                continue
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        submit_button.click()
        
        # Wait for dashboard
        print("4. Waiting for dashboard...")
        dashboard_url = self.config.get('validation', {}).get('dashboardUrl', '**/console/dashboard')
        self.page.wait_for_url(dashboard_url, timeout=timeouts.get('navigation', 10000))
        print("   ✓ Login successful!")
    
    def navigate_to_users(self):
        """Navigate to System page and Users tab"""
        print("\n5. Navigating to System page...")
        
        ui_config = self.config['systemDeactivateUser']['ui']
        timeouts = self.config['systemDeactivateUser']['timeouts']
        
        # Click System nav
        system_nav = self.page.locator(f'[data-testid="{ui_config["systemNavTestId"]}"]')
        expect(system_nav).to_be_visible(timeout=timeouts.get('element', 5000))
        system_nav.click()
        
        # Wait for page load
        self.page.wait_for_load_state("networkidle")
        print("   ✓ On System page")
        
        # Check if we need to click Users tab (it might be default)
        # Try multiple selectors for Users tab
        users_tab_selectors = [
            ui_config['usersTabSelector'],
            '[data-testid="system-tab-users"]',
            '.ant-tabs-tab:has-text("Users")',
            '[role="tab"]:has-text("Users")'
        ]
        
        users_tab = None
        for selector in users_tab_selectors:
            try:
                tab = self.page.locator(selector)
                if tab.is_visible(timeout=1000):
                    users_tab = tab
                    break
            except:
                continue
        
        if users_tab and users_tab.is_visible():
            # Check if it's not already active
            try:
                is_active = users_tab.evaluate("el => el.classList.contains('ant-tabs-tab-active')")
                if not is_active:
                    users_tab.click()
                    print("   ✓ Switched to Users tab")
                    self.page.wait_for_load_state("networkidle")
            except:
                # Just click it anyway
                users_tab.click()
                print("   ✓ Clicked Users tab")
                self.page.wait_for_load_state("networkidle")
        
        # Wait for users table to load - it might be in the content area
        # Try multiple selectors for the table
        table_selectors = [
            ui_config['usersTableSelector'],
            '.ant-table',
            'table',
            '[role="table"]'
        ]
        
        table = None
        for selector in table_selectors:
            try:
                tbl = self.page.locator(selector)
                if tbl.is_visible(timeout=1000):
                    table = tbl
                    break
            except:
                continue
        
        if table:
            print("   ✓ Users table loaded")
        else:
            print("   ⚠ Users table not found, continuing anyway...")
    
    def find_target_user(self):
        """Find a suitable user to deactivate"""
        print("\n6. Finding user to deactivate...")
        
        ui_config = self.config['systemDeactivateUser']['ui']
        test_config = self.config['systemDeactivateUser']['testData']
        
        # If specific user is configured
        if test_config.get('targetUserEmail'):
            self.target_user = test_config['targetUserEmail']
            print(f"   Using configured user: {self.target_user}")
            return self.target_user
        
        # Find first available active user (non-admin)
        user_rows = self.page.locator(ui_config['userRowSelector']).all()
        protected_users = test_config.get('skipProtectedUsers', ['admin@rediacc.io'])
        
        for row in user_rows:
            try:
                # Get user email from row
                email_cell = row.locator('td').nth(0)  # Assuming email is in first column
                if not email_cell.is_visible():
                    continue
                
                user_email = email_cell.text_content().strip()
                
                # Skip protected users
                skip_user = False
                for protected in protected_users:
                    if protected in user_email:
                        skip_user = True
                        break
                
                if skip_user:
                    print(f"   Skipping protected user: {user_email}")
                    continue
                
                # Check if user has deactivate button (meaning they're active)
                deactivate_button = row.locator(f'[data-testid="{ui_config["deactivateButtonPrefix"]}{user_email}"]')
                if deactivate_button.is_visible():
                    self.target_user = user_email
                    print(f"   ✓ Found active user to deactivate: {user_email}")
                    return user_email
                    
            except Exception as e:
                print(f"   Error checking row: {str(e)}")
                continue
        
        print("   ⚠ No suitable user found to deactivate")
        return None
    
    def deactivate_user(self):
        """Deactivate the target user"""
        if not self.target_user:
            print("\n7. No user to deactivate, skipping...")
            return False
        
        print(f"\n7. Deactivating user: {self.target_user}")
        
        ui_config = self.config['systemDeactivateUser']['ui']
        timeouts = self.config['systemDeactivateUser']['timeouts']
        
        # Find and click deactivate button
        deactivate_button = self.page.locator(f'[data-testid="{ui_config["deactivateButtonPrefix"]}{self.target_user}"]')
        
        # Fallback to generic deactivate button in user row
        if not deactivate_button.is_visible():
            user_row = self.page.locator(f'tr:has-text("{self.target_user}")')
            deactivate_button = user_row.locator('button:has-text("Deactivate")').first
        
        if not deactivate_button.is_visible():
            print("   ❌ Deactivate button not found")
            return False
        
        # Click deactivate button
        deactivate_button.click()
        print("   ✓ Deactivate button clicked")
        
        # Wait for confirmation dialog
        print("8. Confirming deactivation...")
        confirm_dialog = self.page.locator(ui_config['confirmDialogSelector'])
        expect(confirm_dialog).to_be_visible(timeout=timeouts.get('confirmDialog', 3000))
        
        # Click Yes button
        yes_button = self.page.locator(ui_config['confirmYesButton'])
        if not yes_button.is_visible():
            # Fallback to generic Yes button
            yes_button = self.page.locator('.ant-popconfirm button:has-text("Yes")').first
        
        yes_button.click()
        print("   ✓ Deactivation confirmed")
        
        # Wait for dialog to close
        expect(confirm_dialog).not_to_be_visible(timeout=timeouts.get('deactivation', 5000))
        
        return True
    
    def validate_deactivation(self):
        """Validate user deactivation success"""
        print("\n9. Validating deactivation...")
        
        if not self.target_user:
            print("   ⚠ No user was deactivated")
            return False
        
        ui_config = self.config['systemDeactivateUser']['ui']
        validation_config = self.config['systemDeactivateUser']['validation']
        timeouts = self.config['systemDeactivateUser']['timeouts']
        
        success = False
        
        # Method 1: Check for success notification
        for selector in validation_config.get('notificationSelectors', []):
            try:
                notification = self.page.locator(selector)
                if notification.is_visible():
                    text = notification.text_content()
                    print(f"   ✓ Notification found: {text}")
                    for indicator in validation_config.get('successIndicators', []):
                        if indicator.replace('.*', '') in text:
                            success = True
                            break
            except:
                continue
        
        # Method 2: Check if deactivate button is gone and status changed
        if validation_config.get('statusChangeVerification', True):
            try:
                # Check if deactivate button is no longer visible
                deactivate_button = self.page.locator(f'[data-testid="{ui_config["deactivateButtonPrefix"]}{self.target_user}"]')
                if not deactivate_button.is_visible():
                    print(f"   ✓ Deactivate button removed for {self.target_user}")
                    success = True
                
                # Check if user row shows inactive status
                user_row = self.page.locator(f'tr:has-text("{self.target_user}")')
                inactive_tag = user_row.locator(ui_config['statusInactiveTag'])
                if inactive_tag.is_visible():
                    print(f"   ✓ User {self.target_user} shows as inactive")
                    success = True
                    
                # Check if activate button appeared (for reactivation)
                activate_button = self.page.locator(f'[data-testid="{ui_config["activateButtonPrefix"]}{self.target_user}"]')
                if activate_button.is_visible():
                    print(f"   ✓ Activate button available for {self.target_user}")
                    success = True
                    
            except Exception as e:
                print(f"   ⚠ Could not verify status change: {str(e)}")
        
        return success
    
    def take_screenshot(self, name="screenshot"):
        """Take screenshot for documentation"""
        screenshots_config = self.config.get('screenshots', {})
        if not screenshots_config.get('enabled', True):
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_dir = Path(__file__).parent / screenshots_config.get('path', './artifacts/screenshots')
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        screenshot_path = screenshot_dir / f"{name}_{timestamp}.png"
        self.page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 Screenshot saved: {screenshot_path}")
    
    def cleanup(self):
        """Cleanup browser resources"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        print("\n✓ Browser closed")
    
    def run(self, playwright: Playwright):
        """Main test execution"""
        try:
            print("=" * 60)
            print("System User Deactivate Test - Smart Version")
            print("=" * 60)
            
            # Setup
            self.setup_browser(playwright)
            
            # Login
            self.login()
            
            # Navigate to Users
            self.navigate_to_users()
            
            # Take screenshot of Users page
            self.take_screenshot("users_page_before")
            
            # Find target user
            self.find_target_user()
            
            # Deactivate user
            deactivated = self.deactivate_user()
            
            # Wait for API processing
            if deactivated:
                self.page.wait_for_timeout(2000)
            
            # Validate
            success = self.validate_deactivation() if deactivated else False
            
            # Take final screenshot
            self.take_screenshot("users_page_after")
            
            # Report result
            print("\n" + "=" * 60)
            if success:
                print("✅ TEST PASSED: User deactivated successfully!")
                print(f"   User: {self.target_user}")
            elif not self.target_user:
                print("⚠️ TEST SKIPPED: No suitable user found to deactivate")
                print("   All users may already be inactive or protected")
            else:
                print("❌ TEST FAILED: User deactivation could not be verified")
            print("=" * 60)
            
            # Keep browser open briefly to see results
            self.page.wait_for_timeout(2000)
            
            return 0 if success or not self.target_user else 1
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            
            # Take error screenshot
            try:
                self.take_screenshot("error")
            except:
                pass
            
            raise
        
        finally:
            self.cleanup()


def main():
    """Entry point"""
    try:
        test = UserDeactivationTest()
        
        with sync_playwright() as playwright:
            exit_code = test.run(playwright)
            sys.exit(exit_code)
            
    except KeyboardInterrupt:
        print("\n⚠ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()