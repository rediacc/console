#!/usr/bin/env python3
"""
System Create User Test - Smart Version
Tests the user creation functionality in Rediacc console
Uses config.json for all settings and credentials
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class UserCreationTest:
    """Smart user creation test with configuration support"""
    
    def __init__(self, config_path="config.json"):
        """Initialize test with configuration"""
        self.config = self.load_config(config_path)
        self.browser = None
        self.context = None
        self.page = None
        self.test_user = None
        
    def load_config(self, config_path):
        """Load configuration from JSON file"""
        config_file = Path(__file__).parent / config_path
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Add systemCreateUser configuration if not exists
        if 'systemCreateUser' not in config:
            config['systemCreateUser'] = {
                "ui": {
                    "systemNavTestId": "main-nav-system",
                    "createUserButtonTestId": "system-create-user-button",
                    "emailInputTestId": "resource-form-field-newUserEmail",
                    "passwordInputTestId": "resource-form-field-newUserPassword",
                    "submitButtonTestId": "resource-form-submit-button",
                    "usersTableSelector": "table.ant-table",
                    "modalSelector": ".ant-modal",
                    "usersTabSelector": "[data-tab-key='users'], button:has-text('Users')"
                },
                "testData": {
                    "emailPrefix": "testuser",
                    "emailDomain": "@rediacc.com",
                    "password": "TestUser@2024#Secure",
                    "generateUnique": True
                },
                "validation": {
                    "successIndicators": [
                        "User created successfully",
                        "User '.*' created successfully",
                        "Successfully created user"
                    ],
                    "errorMessages": [
                        "User already exists",
                        "Invalid email",
                        "Password requirements not met"
                    ],
                    "notificationSelectors": [
                        ".ant-message",
                        ".ant-notification",
                        "[role='alert']"
                    ]
                },
                "timeouts": {
                    "navigation": 10000,
                    "element": 5000,
                    "modalOpen": 3000,
                    "creation": 10000,
                    "validation": 5000
                }
            }
        
        return config
    
    def generate_test_user(self):
        """Generate unique test user credentials"""
        test_config = self.config['systemCreateUser']['testData']
        
        # Check for generateUniqueEmail vs generateUnique
        generate_unique = test_config.get('generateUniqueEmail', test_config.get('generateUnique', True))
        
        if generate_unique:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            email = f"{test_config['emailPrefix']}{timestamp}{test_config['emailDomain']}"
        else:
            email = f"{test_config['emailPrefix']}{test_config['emailDomain']}"
        
        # Get password from config - handle both defaultPassword and password keys
        password = test_config.get('defaultPassword', test_config.get('password', 'TestPassword123!'))
        
        self.test_user = {
            'email': email,
            'password': password
        }
        
        return self.test_user
    
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
        email_selector = f'[data-testid="{login_config.get("emailTestId", "login-email-input")}"]'
        email_input = self.page.locator(email_selector).or_(self.page.locator('input[type="email"]'))
        expect(email_input).to_be_visible(timeout=timeouts.get('element', 5000))
        
        # Fill credentials
        print(f"3. Logging in as {credentials.get('email')}...")
        email_input.fill(credentials.get('email', 'admin@rediacc.io'))
        
        # Password input
        password_selector = f'[data-testid="{login_config.get("passwordTestId", "login-password-input")}"]'
        password_input = self.page.locator(password_selector).or_(self.page.locator('input[type="password"]'))
        password_input.fill(credentials.get('password', 'admin'))
        
        # Submit
        submit_selector = f'[data-testid="{login_config.get("submitButtonTestId", "login-submit-button")}"]'
        submit_button = self.page.locator(submit_selector).or_(self.page.locator('button[type="submit"]'))
        submit_button.click()
        
        # Wait for dashboard
        print("4. Waiting for dashboard...")
        dashboard_url = self.config.get('validation', {}).get('dashboardUrl', '**/console/dashboard')
        self.page.wait_for_url(dashboard_url, timeout=timeouts.get('navigation', 10000))
        print("   ✓ Login successful!")
    
    def navigate_to_system(self):
        """Navigate to System page"""
        print("\n5. Navigating to System page...")
        
        ui_config = self.config['systemCreateUser']['ui']
        timeouts = self.config['systemCreateUser']['timeouts']
        
        # Click System nav
        system_nav = self.page.locator(f'[data-testid="{ui_config["systemNavTestId"]}"]')
        expect(system_nav).to_be_visible(timeout=timeouts.get('elementWait', 5000))
        system_nav.click()
        
        # Wait for page load
        self.page.wait_for_load_state("networkidle")
        
        # Click Users tab if needed
        users_tab = self.page.locator(ui_config.get('usersTabSelector', '[data-tab-key="users"]'))
        if users_tab.is_visible():
            users_tab.click()
            print("   ✓ Switched to Users tab")
        
        print("   ✓ On System page")
    
    def create_user(self):
        """Create a new user"""
        print("\n6. Creating new user...")
        
        ui_config = self.config['systemCreateUser']['ui']
        timeouts = self.config['systemCreateUser']['timeouts']
        
        # Generate test user
        user = self.generate_test_user()
        print(f"   Test user: {user['email']}")
        
        # Click create user button
        create_button = self.page.locator(f'[data-testid="{ui_config["createUserButtonTestId"]}"]')
        expect(create_button).to_be_visible(timeout=timeouts.get('elementWait', 5000))
        create_button.click()
        print("   ✓ Create user modal opened")
        
        # Wait for modal
        modal = self.page.locator(ui_config['modalSelector'])
        expect(modal).to_be_visible(timeout=timeouts['modalOpen'])
        
        # Fill email
        email_input = self.page.locator(f'[data-testid="{ui_config["emailInputTestId"]}"]')
        expect(email_input).to_be_visible(timeout=timeouts.get('elementWait', 5000))
        email_input.fill(user['email'])
        print(f"   ✓ Email filled: {user['email']}")
        
        # Fill password
        password_input = self.page.locator(f'[data-testid="{ui_config["passwordInputTestId"]}"]')
        expect(password_input).to_be_visible(timeout=timeouts.get('elementWait', 5000))
        password_input.fill(user['password'])
        print("   ✓ Password filled")
        
        # Submit
        submit_button = self.page.locator(f'[data-testid="{ui_config["submitButtonTestId"]}"]')
        expect(submit_button).to_be_visible(timeout=timeouts.get('elementWait', 5000))
        submit_button.click()
        print("   ✓ Form submitted")
        
        return user
    
    def validate_creation(self, user):
        """Validate user creation success"""
        print("\n7. Validating user creation...")
        
        ui_config = self.config['systemCreateUser']['ui']
        validation_config = self.config['systemCreateUser']['validation']
        timeouts = self.config['systemCreateUser']['timeouts']
        
        success = False
        
        # Method 1: Check if modal closed
        try:
            modal = self.page.locator(ui_config['modalSelector'])
            expect(modal).not_to_be_visible(timeout=timeouts.get('modalClose', 10000))
            print("   ✓ Modal closed successfully")
            success = True
        except:
            print("   ⚠ Modal still visible")
        
        # Method 2: Check for success notification
        # Handle both array and nested object structure
        notification_selectors = []
        if isinstance(validation_config.get('notificationSelectors'), list):
            notification_selectors = validation_config['notificationSelectors']
        elif 'successIndicators' in validation_config and 'notificationSelectors' in validation_config['successIndicators']:
            notification_selectors = validation_config['successIndicators']['notificationSelectors']
        
        for selector in notification_selectors:
            try:
                notification = self.page.locator(selector)
                if notification.is_visible():
                    text = notification.text_content()
                    print(f"   ✓ Notification found: {text}")
                    # Get success messages
                    success_messages = validation_config.get('successMessages', validation_config.get('successIndicators', []))
                    if isinstance(success_messages, dict):
                        success_messages = []
                    for indicator in success_messages:
                        if indicator.replace('.*', '') in text:
                            success = True
                            break
            except:
                continue
        
        # Method 3: Check if user appears in table
        try:
            table = self.page.locator(ui_config['usersTableSelector'])
            expect(table).to_be_visible(timeout=timeouts.get('tableRefresh', 5000))
            
            # Look for the new user in the table
            user_row = self.page.locator(f'text="{user["email"]}"')
            if user_row.is_visible():
                print(f"   ✓ User {user['email']} found in table")
                success = True
        except:
            print("   ⚠ Could not verify user in table")
        
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
            print("System Create User Test - Smart Version")
            print("=" * 60)
            
            # Setup
            self.setup_browser(playwright)
            
            # Login
            self.login()
            
            # Navigate to System
            self.navigate_to_system()
            
            # Take screenshot of System page
            self.take_screenshot("system_page")
            
            # Create user
            user = self.create_user()
            
            # Wait for API processing
            self.page.wait_for_timeout(2000)
            
            # Validate
            success = self.validate_creation(user)
            
            # Take final screenshot
            self.take_screenshot("user_created")
            
            # Report result
            print("\n" + "=" * 60)
            if success:
                print("✅ TEST PASSED: User created successfully!")
                print(f"   Email: {user['email']}")
            else:
                print("❌ TEST FAILED: User creation could not be verified")
            print("=" * 60)
            
            # Keep browser open briefly to see results
            self.page.wait_for_timeout(2000)
            
            return 0 if success else 1
            
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
        test = UserCreationTest()
        
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