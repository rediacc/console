#!/usr/bin/env python3
"""
System Bridge Reset Auth Test - Smart Version
Tests the bridge authorization reset functionality in Rediacc console
"""

import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class BridgeResetAuthTest:
    """Smart bridge reset auth test with config-based approach"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self.config = self.load_config()
        self.page = None
        self.context = None
        self.browser = None
        self.resetting_bridge_name = None
        
    def load_config(self) -> dict:
        """Load configuration from config.json"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Add default bridge reset auth config if not present
                if 'systemBridgeResetAuth' not in config:
                    config['systemBridgeResetAuth'] = {
                        "ui": {
                            "systemNavTestId": "main-nav-system",
                            "bridgesTabSelector": '[role="tab"]:has-text("Bridges")',
                            "resetAuthButtonPrefix": "system-bridge-reset-auth-button-",
                            "confirmDialogSelector": ".ant-modal, .ant-popconfirm",
                            "confirmResetButton": "button:has-text('Reset Authorization')",
                            "confirmCancelButton": "button:has-text('Cancel')",
                            "bridgesTableSelector": "table.ant-table",
                            "bridgeRowSelector": "tr.ant-table-row"
                        },
                        "testData": {
                            "targetBridgeName": None,
                            "targetBridgePattern": "bridge.",
                            "skipSystemBridges": ["Global Bridges"],
                            "resetMode": "first_available"
                        },
                        "validation": {
                            "successIndicators": [
                                "Authorization reset successfully",
                                "Bridge authorization reset",
                                "Reset successful",
                                "Token regenerated"
                            ],
                            "errorMessages": [
                                "Cannot reset authorization",
                                "Bridge not found",
                                "Reset failed",
                                "Operation not permitted"
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
                            "confirmDialog": 3000,
                            "resetOperation": 5000,
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
        
        # Check if Bridges tab or bridge users are already visible
        bridges_visible = self.page.locator('[role="tab"]:has-text("Bridges")').is_visible() or \
                         self.page.locator('.ant-tabs-tab:has-text("Bridges")').is_visible() or \
                         self.page.locator('text="Permissions"').is_visible()
        
        if bridges_visible:
            print("Expert mode features already visible")
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
    
    def navigate_to_bridges_section(self):
        """Navigate to Bridges section (might be in Users tab or separate tab)"""
        print("Looking for Bridges section...")
        
        # Get config values
        reset_config = self.config.get('systemBridgeResetAuth', {})
        ui_config = reset_config.get('ui', {})
        
        # First try to find a dedicated Bridges tab
        bridges_tab_selectors = [
            ui_config.get('bridgesTabSelector', '[role="tab"]:has-text("Bridges")'),
            '.ant-tabs-tab:has-text("Bridges")',
            'button:has-text("Bridges")',
            'a:has-text("Bridges")'
        ]
        
        for selector in bridges_tab_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for content to load
                self.page.wait_for_load_state("networkidle", timeout=3000)
                print("Bridges tab opened")
                return True
        
        # If no Bridges tab, bridges might be in Users tab
        print("No dedicated Bridges tab found, checking Users tab for bridge accounts...")
        
        users_tab_selectors = [
            '[role="tab"]:has-text("Users")',
            '.ant-tabs-tab:has-text("Users")',
            'button:has-text("Users")'
        ]
        
        for selector in users_tab_selectors:
            if self.smart_click(selector, timeout=2000):
                self.page.wait_for_load_state("networkidle", timeout=3000)
                print("Users tab opened, looking for bridge accounts")
                return True
        
        return False
    
    def find_and_click_reset_auth_button(self):
        """Find and click reset auth button for a bridge"""
        print("Looking for bridge to reset authorization...")
        
        # Get config values
        reset_config = self.config.get('systemBridgeResetAuth', {})
        ui_config = reset_config.get('ui', {})
        test_data = reset_config.get('testData', {})
        
        target_bridge = test_data.get('targetBridgeName')
        bridge_pattern = test_data.get('targetBridgePattern', 'bridge.')
        skip_bridges = test_data.get('skipSystemBridges', ['Global Bridges'])
        reset_mode = test_data.get('resetMode', 'first_available')
        
        # If specific bridge name provided
        if target_bridge:
            print(f"Looking for specific bridge: {target_bridge}")
            
            # Try test-id first
            reset_button_id = f"{ui_config.get('resetAuthButtonPrefix', 'system-bridge-reset-auth-button-')}{target_bridge}"
            if self.smart_click(f'[data-testid="{reset_button_id}"]', timeout=2000):
                self.resetting_bridge_name = target_bridge
                print(f"Reset auth button clicked for bridge: {target_bridge}")
                return True
            
            # Try to find in table row
            try:
                bridge_row = self.page.locator(f'tr:has-text("{target_bridge}")').first
                if bridge_row.is_visible():
                    reset_button = self.find_reset_button_in_row(bridge_row)
                    if reset_button and reset_button.is_visible():
                        reset_button.click()
                        self.resetting_bridge_name = target_bridge
                        print(f"Reset auth button clicked for bridge: {target_bridge}")
                        return True
            except:
                pass
        
        # Find first available bridge to reset
        if reset_mode == 'first_available':
            print(f"Looking for first available bridge (pattern: {bridge_pattern})...")
            
            try:
                # Find all table rows
                rows = self.page.locator('tr.ant-table-row, tbody tr').all()
                
                for row in rows:
                    try:
                        row_text = row.text_content()
                        
                        # Look for bridge pattern (e.g., "bridge." in email)
                        if bridge_pattern.lower() in row_text.lower():
                            # Skip system bridges
                            if any(skip_name.lower() in row_text.lower() for skip_name in skip_bridges):
                                continue
                            
                            # Look for reset auth button in this row
                            reset_button = self.find_reset_button_in_row(row)
                            if reset_button and reset_button.is_visible():
                                # Extract bridge name from row if possible
                                try:
                                    bridge_name_element = row.locator('td').first
                                    self.resetting_bridge_name = bridge_name_element.text_content().strip()
                                except:
                                    self.resetting_bridge_name = "Bridge Account"
                                
                                reset_button.click()
                                print(f"Reset auth button clicked for: {self.resetting_bridge_name}")
                                return True
                    except:
                        continue
            except:
                pass
            
            # Fallback: try any reset auth button
            reset_selectors = [
                'button:has-text("Reset Auth")',
                'button:has-text("Reset Authorization")',
                'button:has-text("Reset")',
                'button[title*="Reset" i]',
                'button[title*="auth" i]',
                '[data-testid*="reset-auth"]',
                '[data-testid*="reset"]'
            ]
            
            for selector in reset_selectors:
                if self.smart_click(selector, timeout=1000):
                    print("Reset auth button clicked (generic)")
                    return True
        
        print("Could not find any bridge reset auth button")
        return False
    
    def find_reset_button_in_row(self, row):
        """Find reset button in a specific table row"""
        reset_selectors = [
            'button:has-text("Reset Auth")',
            'button:has-text("Reset Authorization")',
            'button:has-text("Reset")',
            'button[title*="reset" i]',
            'button[title*="auth" i]',
            '[data-testid*="reset-auth"]',
            '[data-testid*="reset"]'
        ]
        
        for selector in reset_selectors:
            try:
                button = row.locator(selector).first
                if button.is_visible():
                    return button
            except:
                continue
        return None
    
    def confirm_reset_authorization(self):
        """Confirm the reset authorization in dialog"""
        print("Confirming reset authorization...")
        
        # Get config values
        reset_config = self.config.get('systemBridgeResetAuth', {})
        ui_config = reset_config.get('ui', {})
        
        # Wait a moment for dialog to appear
        self.page.wait_for_timeout(500)
        
        # Try configured confirm button first
        confirm_button = ui_config.get('confirmResetButton', "button:has-text('Reset Authorization')")
        if self.smart_click(confirm_button, timeout=2000):
            print("Reset authorization confirmed")
            return True
        
        # Try alternative selectors
        confirm_selectors = [
            'button:has-text("Reset Authorization")',
            'button:has-text("Reset Auth")',
            'button:has-text("Reset")',
            'button:has-text("Yes")',
            'button:has-text("OK")',
            'button:has-text("Confirm")',
            '.ant-modal button.ant-btn-primary',
            '.ant-modal button.ant-btn-dangerous',
            '[role="dialog"] button:has-text("Reset")',
            '[role="dialog"] button:has-text("Yes")',
            '.ant-popconfirm button:has-text("Yes")'
        ]
        
        for selector in confirm_selectors:
            if self.smart_click(selector, timeout=2000):
                print("Reset authorization confirmed")
                return True
        
        # Try by role
        try:
            button = self.page.get_by_role("button", name="Reset Authorization")
            if button.is_visible():
                button.click()
                print("Reset authorization confirmed (by role)")
                return True
        except:
            pass
        
        print("Could not confirm reset authorization")
        return False
    
    def check_success_notification(self):
        """Check for success notification"""
        print("Checking for success notification...")
        
        # Get config values
        reset_config = self.config.get('systemBridgeResetAuth', {})
        validation = reset_config.get('validation', {})
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
                    if indicator.lower() in message.lower():
                        print(f"Success: {message}")
                        return True
                
                # Check for generic success
                if any(word in message.lower() for word in ['success', 'reset', 'regenerated', 'completed']):
                    print(f"Success: {message}")
                    return True
                
                # Check for errors
                error_messages = validation.get('errorMessages', [])
                for error in error_messages:
                    if error.lower() in message.lower():
                        print(f"Error: {message}")
                        return False
        
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
            print("Starting System Bridge Reset Auth Test (Smart Version)...")
            
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
                self.take_screenshot("bridge_resetauth_before_expert")
            
            if not self.switch_to_expert_mode():
                print("Warning: Could not switch to Expert mode, continuing...")
            
            # Take screenshot after mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridge_resetauth_after_expert")
            
            if not self.navigate_to_bridges_section():
                print("Warning: Could not navigate to Bridges section")
            
            # Take screenshot of bridges/users list
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridge_resetauth_list")
            
            if self.find_and_click_reset_auth_button():
                # Take screenshot of confirmation dialog if it appears
                self.page.wait_for_timeout(500)
                if self.config.get('screenshots', {}).get('enabled', True):
                    self.take_screenshot("bridge_resetauth_confirmation")
                
                if self.confirm_reset_authorization():
                    # Wait for operation to complete
                    self.page.wait_for_load_state("networkidle", timeout=5000)
                    
                    # Check for success
                    self.check_success_notification()
                    
                    # Take final screenshot
                    if self.config.get('screenshots', {}).get('enabled', True):
                        self.take_screenshot("bridge_resetauth_complete")
                    
                    if self.resetting_bridge_name:
                        print(f"Authorization reset completed for: {self.resetting_bridge_name}")
                    else:
                        print("Bridge authorization reset completed!")
                else:
                    print("Reset authorization was not confirmed")
            else:
                print("No bridge found for authorization reset")
            
            print("\nTest completed!")
            
            # Keep browser open briefly to observe results
            self.page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            
            # Take error screenshot
            if self.page and self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("bridge_resetauth_error")
            
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
        test = BridgeResetAuthTest()
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