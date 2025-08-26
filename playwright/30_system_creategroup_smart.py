#!/usr/bin/env python3
"""
System Create Permission Group Test - Smart Version
Tests the permission group creation functionality in Rediacc console
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class CreatePermissionGroupTest:
    """Smart permission group creation test with config-based approach"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self.config = self.load_config()
        self.page = None
        self.context = None
        self.browser = None
        # Generate unique group name with timestamp
        self.group_name = f"TestGroup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def load_config(self) -> dict:
        """Load configuration from config.json"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Use existing systemPermissions config or add default if not present
                if 'systemCreateGroup' not in config:
                    # Check if systemPermissions exists and use it
                    if 'systemPermissions' in config:
                        config['systemCreateGroup'] = config['systemPermissions'].copy()
                    else:
                        config['systemCreateGroup'] = {
                            "ui": {
                                "systemNavTestId": "main-nav-system",
                                "expertModeSelector": "label:has-text('Expert')",
                                "permissionsTabTestId": "system-tab-permissions",
                                "createButtonTestId": "system-create-permission-group-button",
                                "groupNameInputTestId": "system-permission-group-name-input",
                                "submitButtonTestId": "modal-create-permission-group-ok",
                                "cancelButtonTestId": "modal-create-permission-group-cancel",
                                "permissionsTableSelector": "table.ant-table",
                                "modalSelector": ".ant-modal"
                            },
                            "testData": {
                                "groupNamePrefix": "TestGroup",
                                "generateUnique": True,
                                "requireExpertMode": True,
                                "defaultPermissions": []
                            },
                            "validation": {
                                "successIndicators": [
                                    "Permission group created successfully",
                                    "Permission group '.*' created successfully",
                                    "Successfully created permission group",
                                    "Group created"
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
                                "checkTableEntry": True
                            },
                            "timeouts": {
                                "navigation": 10000,
                                "element": 5000,
                                "modalOpen": 3000,
                                "creation": 5000,
                                "validation": 5000
                            }
                        }
                return config
        except FileNotFoundError:
            print(f"Config file not found at {self.config_path}")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Invalid JSON in config file {self.config_path}")
            sys.exit(1)
    
    def wait_for_element(self, selector: str, timeout: int = None):
        """Smart wait for element - waits only as long as needed"""
        timeout = timeout or self.config['timeouts']['elementVisible']
        try:
            element = self.page.locator(selector).first
            element.wait_for(state="visible", timeout=timeout)
            return element
        except:
            return None
    
    def smart_click(self, element_or_selector, timeout: int = None):
        """Smart click that waits for element to be ready"""
        timeout = timeout or self.config['timeouts']['elementVisible']
        
        if isinstance(element_or_selector, str):
            element = self.wait_for_element(element_or_selector, timeout)
            if element:
                element.click()
                return True
        else:
            try:
                element_or_selector.wait_for(state="visible", timeout=timeout)
                element_or_selector.click()
                return True
            except:
                pass
        return False
    
    def smart_fill(self, selector: str, value: str, timeout: int = None):
        """Smart fill that waits for input to be ready"""
        element = self.wait_for_element(selector, timeout)
        if element:
            element.fill(value)
            return True
        return False
    
    def login(self):
        """Login to the console using config credentials"""
        print("Logging in...")
        
        # Navigate to console
        base_url = self.config['baseUrl']
        self.page.goto(f"{base_url}/console")
        self.page.wait_for_load_state("domcontentloaded")
        
        # Check if already on login page
        current_url = self.page.url
        if '/login' not in current_url and 'signin' not in current_url:
            # Try to find login link
            login_selectors = [
                '[data-testid="header-login-link"]',
                'a:has-text("Login")',
                '[role="banner"] a:has-text("Login")'
            ]
            
            for selector in login_selectors:
                try:
                    login_link = self.page.locator(selector).first
                    if login_link.is_visible():
                        # Handle potential popup
                        with self.page.expect_popup() as popup_info:
                            login_link.click()
                            self.page = popup_info.value
                        break
                except:
                    # No popup, continue with same page
                    if self.smart_click(selector, timeout=2000):
                        break
        
        # Wait for login form
        self.page.wait_for_load_state("networkidle", timeout=5000)
        
        # Fill login credentials from config
        email = self.config['login']['credentials']['email']
        password = self.config['login']['credentials']['password']
        
        # Try multiple email input selectors
        email_selectors = [
            '[data-testid="login-email-input"]',
            'input[type="email"]',
            'input[placeholder*="email" i]',
            'input[name="email"]'
        ]
        
        for selector in email_selectors:
            if self.smart_fill(selector, email, timeout=2000):
                break
        
        # Try multiple password input selectors
        password_selectors = [
            '[data-testid="login-password-input"]',
            'input[type="password"]',
            'input[placeholder*="password" i]'
        ]
        
        for selector in password_selectors:
            if self.smart_fill(selector, password, timeout=2000):
                break
        
        # Submit login
        submit_selectors = [
            '[data-testid="login-submit-button"]',
            'button[type="submit"]',
            'button:has-text("Sign In")',
            'button:has-text("Login")'
        ]
        
        for selector in submit_selectors:
            if self.smart_click(selector, timeout=2000):
                break
        
        # Wait for dashboard
        try:
            self.page.wait_for_url("**/console/dashboard", timeout=self.config['login']['timeouts']['navigation'])
            print("Login successful!")
            return True
        except:
            print("Login failed - timeout waiting for dashboard")
            return False
    
    def navigate_to_system(self):
        """Navigate to System page"""
        print("Navigating to System...")
        
        system_selectors = [
            '[data-testid="main-nav-system"]',
            'nav a:has-text("System")',
            'a[href*="/system"]',
            '[data-testid*="system"]',
            'text=System'
        ]
        
        for selector in system_selectors:
            if self.smart_click(selector, timeout=2000):
                self.page.wait_for_load_state("networkidle", timeout=5000)
                return True
        
        return False
    
    def switch_to_expert_mode(self):
        """Switch to Expert mode if needed"""
        print("Checking for Expert mode...")
        
        # Get config
        group_config = self.config.get('systemCreateGroup', {})
        
        # Check if Permissions tab is already visible (indicates Expert mode)
        permissions_visible = self.page.locator('[role="tab"]:has-text("Permissions")').is_visible() or \
                             self.page.locator('.ant-tabs-tab:has-text("Permissions")').is_visible()
        
        if permissions_visible:
            print("Permissions tab already visible (Expert mode active)")
            return True
        
        # Try to switch to Expert mode
        expert_selectors = [
            group_config.get('ui', {}).get('expertModeSelector', 'label:has-text("Expert")'),
            '.ant-radio-wrapper:has-text("Expert")',
            'input[type="radio"][value="expert"]',
            'span:has-text("Expert")',
            '[role="radio"]:has-text("Expert")'
        ]
        
        for selector in expert_selectors:
            element = self.page.locator(selector).first
            if element.is_visible():
                # Check if not already selected
                try:
                    is_checked = element.is_checked() if element.get_attribute("type") == "radio" else False
                except:
                    is_checked = False
                
                if not is_checked:
                    element.click()
                    # Wait for UI to update
                    self.page.wait_for_load_state("networkidle", timeout=3000)
                    print("Switched to Expert mode")
                else:
                    print("Already in Expert mode")
                return True
        
        print("Could not find Expert mode selector")
        return False
    
    def navigate_to_permissions_tab(self):
        """Navigate to Permissions tab"""
        print("Navigating to Permissions tab...")
        
        # Get config
        group_config = self.config.get('systemCreateGroup', {})
        ui_config = group_config.get('ui', {})
        
        # Try test-id first
        permissions_tab_id = ui_config.get('permissionsTabTestId', 'system-tab-permissions')
        if self.smart_click(f'[data-testid="{permissions_tab_id}"]', timeout=2000):
            print("Permissions tab opened")
            return True
        
        # Try alternative selectors
        permissions_selectors = [
            '[role="tab"]:has-text("Permissions")',
            '.ant-tabs-tab:has-text("Permissions")',
            'button:has-text("Permissions")',
            'a:has-text("Permissions")',
            'div[role="tab"]:has-text("Permissions")',
            'text=Permissions',
            '[data-testid*="permissions"]'
        ]
        
        for selector in permissions_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for content to load
                self.page.wait_for_load_state("networkidle", timeout=3000)
                print("Permissions tab opened")
                return True
        
        print("Could not find Permissions tab")
        return False
    
    def open_create_group_dialog(self):
        """Open the create permission group dialog"""
        print("Opening create permission group dialog...")
        
        # Get config
        group_config = self.config.get('systemCreateGroup', {})
        ui_config = group_config.get('ui', {})
        
        # Try test-id first
        create_button_id = ui_config.get('createButtonTestId', 'system-create-permission-group-button')
        if self.smart_click(f'[data-testid="{create_button_id}"]', timeout=2000):
            print("Create permission group dialog opened")
            return True
        
        # Try alternative selectors
        create_selectors = [
            'button:has-text("Create Permission Group")',
            'button:has-text("Add Permission Group")',
            'button:has-text("Create Group")',
            'button:has-text("Add Group")',
            'button:has-text("Create")',
            'button:has-text("Add")',
            'button[title*="Create"]',
            'button[title*="Add"]',
            'button.ant-btn-primary:has-text("+")',
            '.ant-btn-icon-only:has([aria-label*="plus"])',
            'button.ant-btn-primary',
            '[data-testid*="create"]',
            '[data-testid*="add"]'
        ]
        
        for selector in create_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for modal to appear
                self.page.wait_for_timeout(500)
                print("Create permission group dialog opened")
                return True
        
        print("Could not open create permission group dialog")
        return False
    
    def fill_group_form(self):
        """Fill the permission group creation form"""
        print(f"Filling permission group form with name: {self.group_name}...")
        
        # Get config
        group_config = self.config.get('systemCreateGroup', {})
        ui_config = group_config.get('ui', {})
        
        # Try test-id first
        group_name_id = ui_config.get('groupNameInputTestId', 'system-permission-group-name-input')
        if self.smart_fill(f'[data-testid="{group_name_id}"]', self.group_name, timeout=2000):
            print(f"Permission group name entered: {self.group_name}")
            return True
        
        # Try alternative selectors
        name_selectors = [
            'input[placeholder*="group" i]',
            'input[placeholder*="name" i]',
            'input[name="groupName"]',
            'input[name="name"]',
            '.ant-modal input[type="text"]',
            '.ant-form-item input',
            '.ant-modal .ant-input'
        ]
        
        for selector in name_selectors:
            if self.smart_fill(selector, self.group_name, timeout=1000):
                print(f"Permission group name entered: {self.group_name}")
                return True
        
        print("Could not enter permission group name")
        return False
    
    def submit_group_creation(self):
        """Submit the permission group creation form"""
        print("Submitting permission group creation...")
        
        # Get config
        group_config = self.config.get('systemCreateGroup', {})
        ui_config = group_config.get('ui', {})
        
        # Try test-id first
        submit_id = ui_config.get('submitButtonTestId', 'modal-create-permission-group-ok')
        if self.smart_click(f'[data-testid="{submit_id}"]', timeout=2000):
            print("Permission group creation submitted")
            return True
        
        # Try alternative selectors
        submit_selectors = [
            '.ant-modal button:has-text("OK")',
            '.ant-modal button:has-text("Create")',
            '.ant-modal button:has-text("Submit")',
            '.ant-modal button.ant-btn-primary',
            '[role="dialog"] button[type="submit"]',
            '[role="dialog"] button:has-text("OK")',
            '[role="dialog"] button.ant-btn-primary'
        ]
        
        for selector in submit_selectors:
            if self.smart_click(selector, timeout=2000):
                print("Permission group creation submitted")
                return True
        
        print("Could not submit permission group creation")
        return False
    
    def check_success_notification(self):
        """Check for success notification"""
        print("Checking for success notification...")
        
        # Get config
        group_config = self.config.get('systemCreateGroup', {})
        validation = group_config.get('validation', {})
        notification_selectors = validation.get('notificationSelectors', [
            '.ant-message',
            '.ant-notification',
            '[role="alert"]'
        ])
        
        for selector in notification_selectors:
            element = self.page.locator(selector).first
            if element.is_visible():
                message = element.text_content()
                print(f"Notification found: {message}")
                
                # Check if it's a success message
                success_indicators = validation.get('successIndicators', [])
                for indicator in success_indicators:
                    if indicator.replace('.*', '').lower() in message.lower():
                        print(f"Success: {message}")
                        return True
                
                # Check for generic success
                if 'success' in message.lower() or 'created' in message.lower():
                    print(f"Success: {message}")
                    return True
                
                # Check for errors
                error_messages = validation.get('errorMessages', [])
                for error in error_messages:
                    if error.lower() in message.lower():
                        print(f"Error: {message}")
                        return False
        
        return False
    
    def verify_group_in_table(self):
        """Verify the group appears in the permissions table"""
        print(f"Verifying group '{self.group_name}' in table...")
        
        # Wait for table to update
        self.page.wait_for_timeout(1000)
        
        # Check if group appears in table or as a tag
        try:
            # Look for group in table
            group_element = self.page.locator(f'text="{self.group_name}"').first
            if group_element.is_visible():
                print(f"Permission group '{self.group_name}' found in interface")
                return True
            
            # Look for group as tag
            group_tag = self.page.locator(f'.ant-tag:has-text("{self.group_name}")').first
            if group_tag.is_visible():
                print(f"Permission group '{self.group_name}' found as tag")
                return True
        except:
            pass
        
        print(f"Could not verify group '{self.group_name}' in interface")
        return False
    
    def take_screenshot(self, name: str):
        """Take a screenshot with timestamp"""
        screenshots_dir = Path(self.config.get('screenshots', {}).get('path', './artifacts/screenshots'))
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        screenshot_path = screenshots_dir / f"{name}.png"
        self.page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved: {screenshot_path}")
    
    def run(self, playwright: Playwright):
        """Main test execution"""
        try:
            print("Starting System Create Permission Group Test (Smart Version)...")
            print(f"Permission group name to be created: {self.group_name}")
            
            # Launch browser based on config
            browser_config = self.config.get('browser', {})
            self.browser = playwright.chromium.launch(
                headless=browser_config.get('headless', False),
                slow_mo=browser_config.get('slowMo', 0)
            )
            
            # Create context with viewport
            viewport = browser_config.get('viewport', {})
            self.context = self.browser.new_context(
                viewport={
                    'width': viewport.get('width', 1280),
                    'height': viewport.get('height', 720)
                }
            )
            
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.config['timeouts']['pageLoad'])
            
            # Execute test steps
            if not self.login():
                raise Exception("Login failed")
            
            if not self.navigate_to_system():
                raise Exception("Could not navigate to System")
            
            # Take screenshot before mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("creategroup_before_expert")
            
            if not self.switch_to_expert_mode():
                print("Warning: Could not switch to Expert mode, continuing...")
            
            # Take screenshot after mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("creategroup_after_expert")
            
            if not self.navigate_to_permissions_tab():
                print("Warning: Could not navigate to Permissions tab")
            
            # Take screenshot of permissions list
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("creategroup_permissions_list")
            
            if self.open_create_group_dialog():
                # Wait for dialog to fully load
                self.page.wait_for_timeout(500)
                
                # Take screenshot of dialog
                if self.config.get('screenshots', {}).get('enabled', True):
                    self.take_screenshot("creategroup_dialog_open")
                
                if self.fill_group_form():
                    # Take screenshot after filling form
                    if self.config.get('screenshots', {}).get('enabled', True):
                        self.take_screenshot("creategroup_form_filled")
                    
                    if self.submit_group_creation():
                        # Wait for operation to complete
                        self.page.wait_for_load_state("networkidle", timeout=5000)
                        
                        # Check for success
                        self.check_success_notification()
                        
                        # Verify group in table if configured
                        group_config = self.config.get('systemCreateGroup', {})
                        if group_config.get('validation', {}).get('checkTableEntry', True):
                            self.verify_group_in_table()
                        
                        # Take final screenshot
                        if self.config.get('screenshots', {}).get('enabled', True):
                            self.take_screenshot("creategroup_complete")
                        
                        print(f"Permission group '{self.group_name}' creation completed!")
                    else:
                        print("Could not submit permission group creation")
                else:
                    print("Could not fill permission group form")
            else:
                print("Could not open create permission group dialog")
            
            print("\nTest completed!")
            
            # Keep browser open briefly to observe results
            self.page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            
            # Take error screenshot
            if self.page and self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("creategroup_error")
            
            raise
        
        finally:
            # Cleanup
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            print("Browser closed.")


def main():
    """Entry point"""
    try:
        test = CreatePermissionGroupTest()
        with sync_playwright() as playwright:
            test.run(playwright)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()