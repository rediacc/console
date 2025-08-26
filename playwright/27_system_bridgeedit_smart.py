#!/usr/bin/env python3
"""
System Bridge Edit Test - Smart Version
Tests the bridge editing functionality in Rediacc console
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class BridgeEditTest:
    """Smart bridge edit test with config-based approach"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self.config = self.load_config()
        self.page = None
        self.context = None
        self.browser = None
        # Generate unique suffix for bridge name
        self.edit_suffix = f"_edited_{datetime.now().strftime('%H%M%S')}"
        
    def load_config(self) -> dict:
        """Load configuration from config.json"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Add default bridge edit config if not present
                if 'systemBridgeEdit' not in config:
                    config['systemBridgeEdit'] = {
                        "ui": {
                            "systemNavTestId": "main-nav-system",
                            "bridgesTabSelector": '[role="tab"]:has-text("Bridges")',
                            "editButtonPrefix": "system-bridge-edit-button-",
                            "bridgeNameInputTestId": "resource-modal-field-bridgeName-input",
                            "submitButtonTestId": "resource-modal-ok-button",
                            "cancelButtonTestId": "resource-modal-cancel-button",
                            "bridgesTableSelector": "table.ant-table",
                            "modalSelector": ".ant-modal"
                        },
                        "testData": {
                            "targetBridgeName": None,
                            "editMode": "first_available",
                            "newBridgeNameSuffix": "_edited",
                            "skipSystemBridges": ["Global Bridges"]
                        },
                        "validation": {
                            "successIndicators": [
                                "Bridge updated successfully",
                                "Bridge '.*' updated successfully",
                                "Successfully updated bridge",
                                "Changes saved"
                            ],
                            "errorMessages": [
                                "Bridge name already exists",
                                "Bridge name is required",
                                "Update failed"
                            ],
                            "notificationSelectors": [
                                ".ant-message",
                                ".ant-notification",
                                "[role='alert']"
                            ],
                            "checkTableAfterEdit": True
                        },
                        "timeouts": {
                            "navigation": 10000,
                            "element": 5000,
                            "modalOpen": 3000,
                            "update": 5000,
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
    
    def clear_and_type(self, element, new_value: str):
        """Clear an input field and type new value"""
        try:
            element.click()
            element.press("Control+a")
            element.type(new_value)
            return True
        except:
            try:
                element.fill("")
                element.fill(new_value)
                return True
            except:
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
        
        # Check if Bridges tab is already visible (indicates Expert mode)
        bridges_visible = self.page.locator('[role="tab"]:has-text("Bridges")').is_visible() or \
                         self.page.locator('.ant-tabs-tab:has-text("Bridges")').is_visible()
        
        if bridges_visible:
            print("Bridges tab already visible (Expert mode active)")
            return True
        
        # Try to switch to Expert mode
        expert_selectors = [
            'label:has-text("Expert")',
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
    
    def navigate_to_bridges_tab(self):
        """Navigate to Bridges tab"""
        print("Navigating to Bridges tab...")
        
        bridges_selectors = [
            '[role="tab"]:has-text("Bridges")',
            '.ant-tabs-tab:has-text("Bridges")',
            'button:has-text("Bridges")',
            'a:has-text("Bridges")',
            'text=Bridges'
        ]
        
        for selector in bridges_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for content to load
                self.page.wait_for_load_state("networkidle", timeout=3000)
                print("Bridges tab opened")
                return True
        
        print("Could not find Bridges tab")
        return False
    
    def find_and_click_edit_button(self):
        """Find and click edit button for a bridge"""
        print("Looking for bridge to edit...")
        
        # Get config values
        bridge_config = self.config.get('systemBridgeEdit', {})
        ui_config = bridge_config.get('ui', {})
        test_data = bridge_config.get('testData', {})
        
        target_bridge = test_data.get('targetBridgeName')
        skip_bridges = test_data.get('skipSystemBridges', ['Global Bridges'])
        edit_mode = test_data.get('editMode', 'first_available')
        
        # Store the bridge name we're editing
        self.editing_bridge_name = None
        
        # Wait for table to be visible
        table_selector = ui_config.get('bridgesTableSelector', 'table.ant-table')
        table = self.wait_for_element(table_selector, timeout=3000)
        
        if not table:
            # Try to find bridges in the specific section
            bridges_section = self.page.locator('text="Bridges in Default Region"').first
            if bridges_section.is_visible():
                print("Found Bridges section")
        
        # If specific bridge name provided
        if target_bridge:
            print(f"Looking for bridge: {target_bridge}")
            
            # Try test-id first
            edit_button_id = f"{ui_config.get('editButtonPrefix', 'system-bridge-edit-button-')}{target_bridge}"
            if self.smart_click(f'[data-testid="{edit_button_id}"]', timeout=2000):
                self.editing_bridge_name = target_bridge
                print(f"Edit button clicked for bridge: {target_bridge}")
                return True
            
            # Try to find in table row
            try:
                bridge_row = self.page.locator(f'tr:has-text("{target_bridge}")').first
                if bridge_row.is_visible():
                    edit_button = bridge_row.locator('button[title*="Edit" i], button:has-text("Edit"), [data-testid*="edit"]').first
                    if edit_button.is_visible():
                        edit_button.click()
                        self.editing_bridge_name = target_bridge
                        print(f"Edit button clicked for bridge: {target_bridge}")
                        return True
            except:
                pass
        
        # Find first available bridge to edit
        if edit_mode == 'first_available':
            print("Looking for first available bridge to edit...")
            
            try:
                # Find all table rows that might contain bridges
                rows = self.page.locator('tr.ant-table-row, tbody tr').all()
                
                for row in rows:
                    try:
                        row_text = row.text_content()
                        
                        # Skip system bridges
                        if any(skip_name.lower() in row_text.lower() for skip_name in skip_bridges):
                            continue
                        
                        # Look for edit button in this row
                        edit_button = row.locator('button[title*="Edit" i], button:has-text("Edit"), [data-testid*="edit"]').first
                        if edit_button.is_visible():
                            # Extract bridge name from row if possible
                            try:
                                bridge_name_element = row.locator('td').first
                                self.editing_bridge_name = bridge_name_element.text_content().strip()
                            except:
                                self.editing_bridge_name = "Unknown Bridge"
                            
                            edit_button.click()
                            print(f"Edit button clicked for bridge: {self.editing_bridge_name}")
                            return True
                    except:
                        continue
            except:
                pass
            
            # Fallback: try any edit button
            edit_selectors = [
                'button[title*="Edit" i]:visible',
                'button:has-text("Edit"):visible',
                '[data-testid*="edit"]:visible',
                '.ant-btn[title*="Edit" i]:visible'
            ]
            
            for selector in edit_selectors:
                if self.smart_click(selector, timeout=1000):
                    print("Edit button clicked (generic)")
                    return True
        
        print("Could not find any bridge edit button")
        return False
    
    def edit_bridge_name(self):
        """Edit the bridge name in the dialog"""
        print("Editing bridge details...")
        
        # Get config values
        bridge_config = self.config.get('systemBridgeEdit', {})
        ui_config = bridge_config.get('ui', {})
        test_data = bridge_config.get('testData', {})
        
        # Wait for modal to be visible
        modal = self.wait_for_element(ui_config.get('modalSelector', '.ant-modal'), timeout=3000)
        if not modal:
            print("Edit modal did not appear")
            return False
        
        # Generate new bridge name
        if self.editing_bridge_name:
            new_bridge_name = f"{self.editing_bridge_name}{self.edit_suffix}"
        else:
            new_bridge_name = f"bridge{self.edit_suffix}"
        
        print(f"Changing bridge name to: {new_bridge_name}")
        
        # Try test-id first
        bridge_name_id = ui_config.get('bridgeNameInputTestId', 'resource-modal-field-bridgeName-input')
        bridge_input = self.page.locator(f'[data-testid="{bridge_name_id}"]').first
        
        if bridge_input.is_visible():
            if self.clear_and_type(bridge_input, new_bridge_name):
                print(f"Bridge name changed to: {new_bridge_name}")
                return True
        
        # Try alternative selectors
        name_selectors = [
            'input[placeholder*="bridge" i]',
            'input[placeholder*="name" i]',
            'input[id*="bridgeName"]',
            'input[name="bridgeName"]',
            '.ant-form-item:has-text("Bridge Name") input',
            '.ant-form-item:has-text("Name") input',
            '.ant-modal input[type="text"]:visible'
        ]
        
        for selector in name_selectors:
            try:
                input_element = self.page.locator(selector).first
                if input_element.is_visible():
                    if self.clear_and_type(input_element, new_bridge_name):
                        print(f"Bridge name changed to: {new_bridge_name}")
                        return True
            except:
                continue
        
        print("Could not find bridge name input field")
        return False
    
    def submit_bridge_edit(self):
        """Submit the bridge edit form"""
        print("Submitting bridge edit...")
        
        # Get config values
        bridge_config = self.config.get('systemBridgeEdit', {})
        ui_config = bridge_config.get('ui', {})
        
        # Try test-id first
        submit_id = ui_config.get('submitButtonTestId', 'resource-modal-ok-button')
        if self.smart_click(f'[data-testid="{submit_id}"]', timeout=2000):
            print("Bridge edit submitted")
            return True
        
        # Try alternative selectors
        submit_selectors = [
            '.ant-modal button:has-text("OK")',
            '.ant-modal button:has-text("Save")',
            '.ant-modal button:has-text("Update")',
            '.ant-modal button:has-text("Submit")',
            '.ant-modal button.ant-btn-primary',
            '[role="dialog"] button[type="submit"]',
            '[role="dialog"] button:has-text("OK")',
            '[role="dialog"] button.ant-btn-primary'
        ]
        
        for selector in submit_selectors:
            if self.smart_click(selector, timeout=2000):
                print("Bridge edit submitted")
                return True
        
        print("Could not submit bridge edit")
        return False
    
    def check_success_notification(self):
        """Check for success notification"""
        print("Checking for success notification...")
        
        # Get config values
        bridge_config = self.config.get('systemBridgeEdit', {})
        validation = bridge_config.get('validation', {})
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
                if 'success' in message.lower() or 'updated' in message.lower() or 'saved' in message.lower():
                    print(f"Success: {message}")
                    return True
        
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
            print("Starting System Bridge Edit Test (Smart Version)...")
            
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
                self.take_screenshot("bridgeedit_before_expert")
            
            if not self.switch_to_expert_mode():
                print("Warning: Could not switch to Expert mode, continuing...")
            
            # Take screenshot after mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridgeedit_after_expert")
            
            if not self.navigate_to_bridges_tab():
                print("Warning: Could not navigate to Bridges tab")
            
            # Take screenshot of bridges list
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridgeedit_bridges_list")
            
            if self.find_and_click_edit_button():
                # Wait for dialog to fully load
                self.page.wait_for_timeout(500)
                
                # Take screenshot of edit dialog
                if self.config.get('screenshots', {}).get('enabled', True):
                    self.take_screenshot("bridgeedit_dialog_open")
                
                if self.edit_bridge_name():
                    # Take screenshot after editing
                    if self.config.get('screenshots', {}).get('enabled', True):
                        self.take_screenshot("bridgeedit_form_edited")
                    
                    if self.submit_bridge_edit():
                        # Wait for operation to complete
                        self.page.wait_for_load_state("networkidle", timeout=5000)
                        
                        # Check for success
                        self.check_success_notification()
                        
                        # Take final screenshot
                        if self.config.get('screenshots', {}).get('enabled', True):
                            self.take_screenshot("bridgeedit_complete")
                        
                        print("Bridge edit completed!")
                    else:
                        print("Could not submit bridge edit")
                else:
                    print("Could not edit bridge details")
            else:
                print("Could not find bridge to edit")
            
            print("\nTest completed!")
            
            # Keep browser open briefly to observe results
            self.page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            
            # Take error screenshot
            if self.page and self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridgeedit_error")
            
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
        test = BridgeEditTest()
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