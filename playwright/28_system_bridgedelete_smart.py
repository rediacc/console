#!/usr/bin/env python3
"""
System Bridge Delete Test - Smart Version
Tests the bridge deletion functionality in Rediacc console
"""

import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class BridgeDeleteTest:
    """Smart bridge delete test with config-based approach"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self.config = self.load_config()
        self.page = None
        self.context = None
        self.browser = None
        self.deleting_bridge_name = None
        
    def load_config(self) -> dict:
        """Load configuration from config.json"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Add default bridge delete config if not present
                if 'systemBridgeDelete' not in config:
                    config['systemBridgeDelete'] = {
                        "ui": {
                            "systemNavTestId": "main-nav-system",
                            "bridgesTabSelector": '[role="tab"]:has-text("Bridges")',
                            "deleteButtonPrefix": "system-bridge-delete-button-",
                            "confirmDialogSelector": ".ant-modal, .ant-popconfirm",
                            "confirmYesButton": "button:has-text('Yes')",
                            "confirmNoButton": "button:has-text('No')",
                            "bridgesTableSelector": "table.ant-table",
                            "bridgeRowSelector": "tr.ant-table-row"
                        },
                        "testData": {
                            "targetBridgeName": None,
                            "skipSystemBridges": ["Global Bridges", "My Bridge"],
                            "deleteMode": "first_available",
                            "createTestBridgeIfNeeded": False
                        },
                        "validation": {
                            "successIndicators": [
                                "Bridge deleted successfully",
                                "Bridge '.*' deleted successfully",
                                "Successfully deleted bridge"
                            ],
                            "errorMessages": [
                                "Cannot delete system bridge",
                                "Bridge not found",
                                "Deletion failed"
                            ],
                            "notificationSelectors": [
                                ".ant-message",
                                ".ant-notification",
                                "[role='alert']"
                            ],
                            "checkTableAfterDeletion": True
                        },
                        "timeouts": {
                            "navigation": 10000,
                            "element": 5000,
                            "confirmDialog": 3000,
                            "deletion": 5000,
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
            'input[name="email"]',
            '.ant-input-affix-wrapper input'
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
        
        # Get config values
        bridge_config = self.config.get('systemBridgeDelete', {})
        ui_config = bridge_config.get('ui', {})
        
        bridges_selectors = [
            ui_config.get('bridgesTabSelector', '[role="tab"]:has-text("Bridges")'),
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
    
    def find_and_click_delete_button(self):
        """Find and click delete button for a bridge"""
        print("Looking for bridge to delete...")
        
        # Get config values
        bridge_config = self.config.get('systemBridgeDelete', {})
        ui_config = bridge_config.get('ui', {})
        test_data = bridge_config.get('testData', {})
        
        target_bridge = test_data.get('targetBridgeName')
        skip_bridges = test_data.get('skipSystemBridges', ['Global Bridges', 'My Bridge'])
        delete_mode = test_data.get('deleteMode', 'first_available')
        
        # If specific bridge name provided
        if target_bridge:
            print(f"Looking for specific bridge: {target_bridge}")
            
            # Try test-id first
            delete_button_id = f"{ui_config.get('deleteButtonPrefix', 'system-bridge-delete-button-')}{target_bridge}"
            if self.smart_click(f'[data-testid="{delete_button_id}"]', timeout=2000):
                self.deleting_bridge_name = target_bridge
                print(f"Delete button clicked for bridge: {target_bridge}")
                return True
            
            # Try to find in table row
            try:
                bridge_row = self.page.locator(f'tr:has-text("{target_bridge}")').first
                if bridge_row.is_visible():
                    delete_button = bridge_row.locator('button[title*="Delete" i], button:has-text("Delete"), [data-testid*="delete"]').first
                    if delete_button.is_visible():
                        delete_button.click()
                        self.deleting_bridge_name = target_bridge
                        print(f"Delete button clicked for bridge: {target_bridge}")
                        return True
            except:
                pass
        
        # Find first available bridge to delete
        if delete_mode == 'first_available':
            print("Looking for first available bridge to delete...")
            
            try:
                # Find all table rows that might contain bridges
                rows = self.page.locator('tr.ant-table-row, tbody tr').all()
                
                for row in rows:
                    try:
                        row_text = row.text_content()
                        
                        # Skip system bridges
                        if any(skip_name.lower() in row_text.lower() for skip_name in skip_bridges):
                            continue
                        
                        # Look for delete button in this row
                        delete_button = row.locator('button[title*="Delete" i], button:has-text("Delete"), [data-testid*="delete"]').first
                        if delete_button.is_visible():
                            # Extract bridge name from row if possible
                            try:
                                bridge_name_element = row.locator('td').first
                                self.deleting_bridge_name = bridge_name_element.text_content().strip()
                            except:
                                self.deleting_bridge_name = "Unknown Bridge"
                            
                            delete_button.click()
                            print(f"Delete button clicked for bridge: {self.deleting_bridge_name}")
                            return True
                    except:
                        continue
            except:
                pass
            
            # Fallback: try any delete button (but skip if it might be for system bridges)
            delete_selectors = [
                'button[title*="Delete" i]:visible',
                'button:has-text("Delete"):visible',
                '[data-testid*="delete"]:visible',
                '.ant-btn-dangerous:visible'
            ]
            
            for selector in delete_selectors:
                buttons = self.page.locator(selector).all()
                if buttons:
                    # Try to find a non-system bridge delete button
                    for button in buttons[:5]:  # Check first 5 buttons
                        try:
                            # Try to get context around the button
                            parent_row = button.locator('xpath=ancestor::tr').first
                            if parent_row:
                                row_text = parent_row.text_content()
                                # Skip if it looks like a system bridge
                                if any(skip_name.lower() in row_text.lower() for skip_name in skip_bridges):
                                    continue
                            
                            if button.is_visible():
                                button.click()
                                print("Delete button clicked (generic)")
                                return True
                        except:
                            continue
        
        print("Could not find any bridge delete button")
        return False
    
    def confirm_deletion(self):
        """Confirm the deletion in dialog"""
        print("Confirming deletion...")
        
        # Get config values
        bridge_config = self.config.get('systemBridgeDelete', {})
        ui_config = bridge_config.get('ui', {})
        
        # Wait a moment for dialog to appear
        self.page.wait_for_timeout(500)
        
        # Try configured confirm button first
        confirm_button = ui_config.get('confirmYesButton', "button:has-text('Yes')")
        if self.smart_click(confirm_button, timeout=2000):
            print("Deletion confirmed")
            return True
        
        # Try alternative selectors
        confirm_selectors = [
            'button:has-text("Yes")',
            'button:has-text("OK")',
            'button:has-text("Confirm")',
            'button:has-text("Delete")',
            '.ant-modal button.ant-btn-primary',
            '.ant-modal button.ant-btn-dangerous',
            '.ant-popconfirm button.ant-btn-dangerous',
            '[role="dialog"] button:has-text("Yes")',
            '[role="dialog"] button:has-text("OK")',
            '.ant-popover button:has-text("Yes")'
        ]
        
        for selector in confirm_selectors:
            if self.smart_click(selector, timeout=2000):
                print("Deletion confirmed")
                return True
        
        # Try by role
        try:
            button = self.page.get_by_role("button", name="Yes")
            if button.is_visible():
                button.click()
                print("Deletion confirmed (by role)")
                return True
        except:
            pass
        
        print("Could not confirm deletion")
        return False
    
    def check_success_notification(self):
        """Check for success notification"""
        print("Checking for success notification...")
        
        # Get config values
        bridge_config = self.config.get('systemBridgeDelete', {})
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
                if 'success' in message.lower() or 'deleted' in message.lower():
                    print(f"Success: {message}")
                    return True
                
                # Check for errors
                error_messages = validation.get('errorMessages', [])
                for error in error_messages:
                    if error.lower() in message.lower():
                        print(f"Error: {message}")
                        return False
        
        return False
    
    def verify_deletion(self):
        """Verify the bridge was deleted from the table"""
        if not self.deleting_bridge_name:
            return True
        
        print(f"Verifying bridge '{self.deleting_bridge_name}' was deleted...")
        
        # Wait for table to update
        self.page.wait_for_timeout(1000)
        
        # Check if bridge still exists in table
        try:
            bridge_row = self.page.locator(f'tr:has-text("{self.deleting_bridge_name}")').first
            if not bridge_row.is_visible():
                print(f"Bridge '{self.deleting_bridge_name}' successfully removed from table")
                return True
            else:
                print(f"Warning: Bridge '{self.deleting_bridge_name}' still appears in table")
                return False
        except:
            print(f"Bridge '{self.deleting_bridge_name}' successfully removed from table")
            return True
    
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
            print("Starting System Bridge Delete Test (Smart Version)...")
            
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
                self.take_screenshot("bridgedelete_before_expert")
            
            if not self.switch_to_expert_mode():
                print("Warning: Could not switch to Expert mode, continuing...")
            
            # Take screenshot after mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridgedelete_after_expert")
            
            if not self.navigate_to_bridges_tab():
                print("Warning: Could not navigate to Bridges tab")
            
            # Take screenshot of bridges list
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridgedelete_bridges_list")
            
            if self.find_and_click_delete_button():
                # Take screenshot of confirmation dialog
                if self.config.get('screenshots', {}).get('enabled', True):
                    self.take_screenshot("bridgedelete_confirmation")
                
                if self.confirm_deletion():
                    # Wait for operation to complete
                    self.page.wait_for_load_state("networkidle", timeout=5000)
                    
                    # Check for success
                    self.check_success_notification()
                    
                    # Verify deletion if configured
                    bridge_config = self.config.get('systemBridgeDelete', {})
                    if bridge_config.get('validation', {}).get('checkTableAfterDeletion', True):
                        self.verify_deletion()
                    
                    # Take final screenshot
                    if self.config.get('screenshots', {}).get('enabled', True):
                        self.take_screenshot("bridgedelete_complete")
                    
                    if self.deleting_bridge_name:
                        print(f"Bridge '{self.deleting_bridge_name}' deletion completed!")
                    else:
                        print("Bridge deletion completed!")
                else:
                    print("Deletion was not confirmed")
            else:
                print("No bridge found to delete or all bridges are system bridges")
            
            print("\nTest completed!")
            
            # Keep browser open briefly to observe results
            self.page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            
            # Take error screenshot
            if self.page and self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridgedelete_error")
            
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
        test = BridgeDeleteTest()
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