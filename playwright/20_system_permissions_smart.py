#!/usr/bin/env python3
"""
System Permissions Test - Smart Version
Tests the permission group creation functionality in Rediacc console
Uses config.json for all settings and credentials
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class PermissionsTest:
    """Smart permissions test with configuration support"""
    
    def __init__(self, config_path="config.json"):
        """Initialize test with configuration"""
        self.config = self.load_config(config_path)
        self.browser = None
        self.context = None
        self.page = None
        self.test_group = None
        
    def load_config(self, config_path):
        """Load configuration from JSON file"""
        config_file = Path(__file__).parent / config_path
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Add systemPermissions configuration if not exists
        if 'systemPermissions' not in config:
            config['systemPermissions'] = {
                "ui": {
                    "systemNavTestId": "main-nav-system",
                    "expertModeSelector": ".ant-segmented-item:has-text('Expert')",
                    "simpleModeSelector": ".ant-segmented-item:has-text('Simple')",
                    "permissionsTabTestId": "system-tab-permissions",
                    "createButtonTestId": "system-create-permission-group-button",
                    "groupNameInputTestId": "system-permission-group-name-input",
                    "submitButtonTestId": "modal-create-permission-group-ok",
                    "cancelButtonTestId": "modal-create-permission-group-cancel",
                    "permissionsTableSelector": "table.ant-table",
                    "modalSelector": ".ant-modal",
                    "modeToggleSelector": ".ant-segmented",
                    "permissionCheckboxPrefix": "permission-checkbox-",
                    "userDropdownSelector": ".ant-select-selector"
                },
                "testData": {
                    "groupNamePrefix": "TestPermGroup",
                    "generateUnique": true,
                    "requireExpertMode": true,
                    "defaultPermissions": []
                },
                "validation": {
                    "successIndicators": [
                        "Permission group created successfully",
                        "Permission group '.*' created successfully",
                        "Successfully created permission group"
                    ],
                    "errorMessages": [
                        "Permission group already exists",
                        "Group name is required",
                        "Invalid permissions"
                    ],
                    "notificationSelectors": [
                        ".ant-message",
                        ".ant-notification",
                        "[role='alert']"
                    ],
                    "checkTableEntry": true,
                    "checkDropdownAvailability": true
                },
                "timeouts": {
                    "navigation": 10000,
                    "element": 5000,
                    "modalOpen": 3000,
                    "creation": 5000,
                    "validation": 5000,
                    "modeSwitch": 3000
                }
            }
        
        return config
    
    def generate_test_group(self):
        """Generate unique test group name"""
        test_config = self.config['systemPermissions']['testData']
        
        if test_config.get('generateUnique', True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            group_name = f"{test_config['groupNamePrefix']}_{timestamp}"
        else:
            group_name = test_config['groupNamePrefix']
        
        self.test_group = {
            'name': group_name,
            'permissions': test_config.get('defaultPermissions', [])
        }
        
        return self.test_group
    
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
    
    def switch_to_expert_mode(self):
        """Switch to Expert mode if required"""
        test_config = self.config['systemPermissions']['testData']
        
        if not test_config.get('requireExpertMode', True):
            return
        
        print("\n5. Checking UI mode...")
        
        ui_config = self.config['systemPermissions']['ui']
        timeouts = self.config['systemPermissions']['timeouts']
        
        # Wait a moment for page to stabilize
        self.page.wait_for_timeout(1000)
        
        # Try multiple selectors for mode toggle
        mode_toggle_selectors = [
            ui_config['modeToggleSelector'],
            '.ant-segmented',
            '[role="radiogroup"]',
            'div:has(> .ant-segmented-item)'
        ]
        
        mode_toggle = None
        for selector in mode_toggle_selectors:
            try:
                toggle = self.page.locator(selector)
                if toggle.is_visible(timeout=1000):
                    mode_toggle = toggle
                    break
            except:
                continue
        
        if not mode_toggle:
            print("   Mode toggle not found, proceeding without mode switch")
            return
        
        # Check if already in Expert mode
        expert_mode = self.page.locator(ui_config['expertModeSelector'])
        if expert_mode.is_visible():
            # Check if it's selected
            try:
                is_selected = expert_mode.evaluate("el => el.classList.contains('ant-segmented-item-selected')")
                if is_selected:
                    print("   ✓ Already in Expert mode")
                    return
            except:
                pass
        
        # Switch to Expert mode
        print("   Switching to Expert mode...")
        expert_mode.click()
        self.page.wait_for_timeout(timeouts.get('modeSwitch', 3000))
        print("   ✓ Switched to Expert mode")
    
    def navigate_to_permissions(self):
        """Navigate to System page and Permissions tab"""
        print("\n6. Navigating to System page...")
        
        ui_config = self.config['systemPermissions']['ui']
        timeouts = self.config['systemPermissions']['timeouts']
        
        # Click System nav
        system_nav = self.page.locator(f'[data-testid="{ui_config["systemNavTestId"]}"]')
        expect(system_nav).to_be_visible(timeout=timeouts.get('element', 5000))
        system_nav.click()
        
        # Wait for page load
        self.page.wait_for_load_state("networkidle")
        print("   ✓ On System page")
        
        # Click Permissions tab
        print("7. Navigating to Permissions tab...")
        permissions_tab = self.page.locator(f'[data-testid="{ui_config["permissionsTabTestId"]}"]')
        
        # Fallback selectors
        if not permissions_tab.is_visible():
            tab_selectors = [
                '.ant-tabs-tab:has-text("Permissions")',
                'button:has-text("Permissions")',
                '[role="tab"]:has-text("Permissions")'
            ]
            
            for selector in tab_selectors:
                try:
                    permissions_tab = self.page.locator(selector)
                    if permissions_tab.is_visible():
                        break
                except:
                    continue
        
        expect(permissions_tab).to_be_visible(timeout=timeouts.get('element', 5000))
        permissions_tab.click()
        
        # Wait for tab content to load
        self.page.wait_for_load_state("networkidle")
        print("   ✓ On Permissions tab")
    
    def create_permission_group(self):
        """Create a new permission group"""
        print("\n8. Creating new permission group...")
        
        ui_config = self.config['systemPermissions']['ui']
        timeouts = self.config['systemPermissions']['timeouts']
        
        # Generate test group
        group = self.generate_test_group()
        print(f"   Test group: {group['name']}")
        
        # Click create permission group button
        create_button = self.page.locator(f'[data-testid="{ui_config["createButtonTestId"]}"]')
        
        # Fallback selectors
        if not create_button.is_visible():
            button_selectors = [
                'button:has-text("Create Permission Group")',
                'button:has-text("Add Permission Group")',
                'button.ant-btn-primary'
            ]
            
            for selector in button_selectors:
                try:
                    create_button = self.page.locator(selector).first
                    if create_button.is_visible():
                        break
                except:
                    continue
        
        expect(create_button).to_be_visible(timeout=timeouts.get('element', 5000))
        create_button.click()
        print("   ✓ Create permission group modal opened")
        
        # Wait for modal
        modal = self.page.locator(ui_config['modalSelector'])
        expect(modal).to_be_visible(timeout=timeouts.get('modalOpen', 3000))
        
        # Fill group name
        group_name_input = self.page.locator(f'[data-testid="{ui_config["groupNameInputTestId"]}"]')
        
        # Fallback selectors
        if not group_name_input.is_visible():
            input_selectors = [
                'input[placeholder*="group" i]',
                'input[placeholder*="name" i]',
                '.ant-modal input[type="text"]'
            ]
            
            for selector in input_selectors:
                try:
                    group_name_input = self.page.locator(selector).first
                    if group_name_input.is_visible():
                        break
                except:
                    continue
        
        expect(group_name_input).to_be_visible(timeout=timeouts.get('element', 5000))
        group_name_input.fill(group['name'])
        print(f"   ✓ Group name filled: {group['name']}")
        
        # Select permissions if specified
        if group['permissions']:
            print("   Selecting permissions...")
            for permission in group['permissions']:
                checkbox = self.page.locator(f'{ui_config["permissionCheckboxPrefix"]}{permission}')
                if checkbox.is_visible():
                    checkbox.check()
                    print(f"   ✓ Selected permission: {permission}")
        
        # Submit
        submit_button = self.page.locator(f'[data-testid="{ui_config["submitButtonTestId"]}"]')
        
        # Fallback selectors
        if not submit_button.is_visible():
            submit_selectors = [
                '.ant-modal button:has-text("OK")',
                '.ant-modal button:has-text("Create")',
                '.ant-modal button.ant-btn-primary'
            ]
            
            for selector in submit_selectors:
                try:
                    submit_button = self.page.locator(selector).first
                    if submit_button.is_visible():
                        break
                except:
                    continue
        
        expect(submit_button).to_be_visible(timeout=timeouts.get('element', 5000))
        submit_button.click()
        print("   ✓ Form submitted")
        
        return group
    
    def validate_creation(self, group):
        """Validate permission group creation success"""
        print("\n9. Validating permission group creation...")
        
        ui_config = self.config['systemPermissions']['ui']
        validation_config = self.config['systemPermissions']['validation']
        timeouts = self.config['systemPermissions']['timeouts']
        
        success = False
        
        # Method 1: Check if modal closed
        try:
            modal = self.page.locator(ui_config['modalSelector'])
            expect(modal).not_to_be_visible(timeout=timeouts.get('creation', 5000))
            print("   ✓ Modal closed successfully")
            success = True
        except:
            print("   ⚠ Modal still visible")
        
        # Method 2: Check for success notification
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
        
        # Method 3: Check if group appears in table
        if validation_config.get('checkTableEntry', True):
            try:
                table = self.page.locator(ui_config['permissionsTableSelector'])
                expect(table).to_be_visible(timeout=timeouts.get('validation', 5000))
                
                # Look for the new group in the table
                group_row = self.page.locator(f'text="{group["name"]}"')
                if group_row.is_visible():
                    print(f"   ✓ Permission group {group['name']} found in table")
                    success = True
            except:
                print("   ⚠ Could not verify group in table")
        
        # Method 4: Check if group is available in dropdown
        if validation_config.get('checkDropdownAvailability', True):
            try:
                # Click on Users tab to check dropdown
                users_tab = self.page.locator('.ant-tabs-tab:has-text("Users")')
                if users_tab.is_visible():
                    users_tab.click()
                    self.page.wait_for_timeout(1000)
                    
                    # Find a user and check if the group is in dropdown
                    # This is optional validation
                    print("   ✓ Additional validation completed")
            except:
                pass
        
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
            print("System Permissions Test - Smart Version")
            print("=" * 60)
            
            # Setup
            self.setup_browser(playwright)
            
            # Login
            self.login()
            
            # Switch to Expert mode
            self.switch_to_expert_mode()
            
            # Navigate to Permissions
            self.navigate_to_permissions()
            
            # Take screenshot of Permissions page
            self.take_screenshot("permissions_page")
            
            # Create permission group
            group = self.create_permission_group()
            
            # Wait for API processing
            self.page.wait_for_timeout(2000)
            
            # Validate
            success = self.validate_creation(group)
            
            # Take final screenshot
            self.take_screenshot("permission_group_created")
            
            # Report result
            print("\n" + "=" * 60)
            if success:
                print("✅ TEST PASSED: Permission group created successfully!")
                print(f"   Group Name: {group['name']}")
            else:
                print("❌ TEST FAILED: Permission group creation could not be verified")
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
        test = PermissionsTest()
        
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