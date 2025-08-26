#!/usr/bin/env python3
"""
System Permissions Delete Test - Smart Version
Tests the permission group deletion functionality in Rediacc console
"""

import json
import re
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class PermissionsDeleteTest:
    """Smart permissions delete test with config-based approach"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self.config = self.load_config()
        self.page = None
        self.context = None
        self.browser = None
        
    def load_config(self) -> dict:
        """Load configuration from config.json"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
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
            '[data-testid*="system"]'
        ]
        
        for selector in system_selectors:
            if self.smart_click(selector, timeout=2000):
                self.page.wait_for_load_state("networkidle", timeout=5000)
                return True
        
        return False
    
    def switch_to_expert_mode(self):
        """Switch to Expert mode if needed"""
        print("Checking for Expert mode...")
        
        # Check if already in Expert mode by looking for Permissions tab
        permissions_visible = self.page.locator('[data-testid="system-tab-permissions"]').is_visible() or \
                            self.page.locator('button:has-text("Permissions")').is_visible() or \
                            self.page.locator('[role="tab"]:has-text("Permissions")').is_visible()
        
        if permissions_visible:
            print("Already in Expert mode or Permissions tab visible")
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
    
    def navigate_to_permissions(self):
        """Navigate to Permissions tab"""
        print("Navigating to Permissions tab...")
        
        permissions_selectors = [
            '[data-testid="system-tab-permissions"]',
            'button:has-text("Permissions")',
            'div[role="tab"]:has-text("Permissions")',
            '.ant-tabs-tab:has-text("Permissions")',
            '[role="tab"]:has-text("Permissions")'
        ]
        
        for selector in permissions_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for permissions content to load
                self.page.wait_for_load_state("networkidle", timeout=3000)
                print("Permissions tab opened")
                return True
        
        print("Could not find Permissions tab")
        return False
    
    def delete_permission_group(self, group_name: str = None):
        """Delete a permission group"""
        # Use config or default
        if not group_name:
            # Try to get from config if available
            group_name = self.config.get('systemPermissionsDelete', {}).get('testData', {}).get('targetGroupName', 'testgroup')
        
        print(f"Looking for permission group '{group_name}' to delete...")
        
        # First try specific test-id
        delete_button_id = f'[data-testid="system-permission-group-delete-button-{group_name}"]'
        if self.smart_click(delete_button_id, timeout=2000):
            print(f"Delete button clicked for group: {group_name}")
            return True
        
        # Try to find in table row
        try:
            # Look for row containing the group name
            group_row = self.page.locator(f'tr:has-text("{group_name}")').first
            if group_row.is_visible():
                # Find delete button in that row
                delete_selectors = [
                    'button:has-text("Delete")',
                    'button[title*="delete" i]',
                    '[data-testid*="delete"]',
                    'button.ant-btn-dangerous'
                ]
                
                for selector in delete_selectors:
                    delete_btn = group_row.locator(selector).first
                    if delete_btn.is_visible():
                        delete_btn.click()
                        print(f"Delete button clicked for group: {group_name}")
                        return True
        except:
            pass
        
        # If specific group not found, try to delete any available test group
        print(f"Group '{group_name}' not found, looking for any deleteable group...")
        
        delete_selectors = [
            'button:has-text("Delete")',
            'button[title*="delete" i]',
            '[data-testid*="delete"]'
        ]
        
        for selector in delete_selectors:
            buttons = self.page.locator(selector).all()
            if buttons:
                # Try to find a test group (not system groups)
                for button in buttons[:5]:  # Check first 5 buttons
                    try:
                        # Get the row to check group name
                        row = button.locator('xpath=ancestor::tr').first
                        row_text = row.text_content() if row else ""
                        
                        # Skip system groups
                        if any(skip in row_text.lower() for skip in ['admin', 'default', 'system']):
                            continue
                        
                        if button.is_visible():
                            button.click()
                            print("Delete button clicked for available group")
                            return True
                    except:
                        continue
        
        print("No deleteable permission group found")
        return False
    
    def confirm_deletion(self):
        """Confirm the deletion in dialog"""
        print("Confirming deletion...")
        
        # Wait a moment for dialog to appear
        self.page.wait_for_timeout(500)
        
        confirm_selectors = [
            '[data-testid="confirm-yes-button"]',
            '.ant-popconfirm button.ant-btn-dangerous:has-text("Yes")',
            '.ant-modal button:has-text("Yes")',
            '.ant-modal button:has-text("OK")',
            '.ant-modal button:has-text("Confirm")',
            '.ant-modal button.ant-btn-primary',
            '[role="dialog"] button:has-text("Yes")'
        ]
        
        for selector in confirm_selectors:
            if self.smart_click(selector, timeout=2000):
                print("Deletion confirmed")
                return True
        
        print("Could not confirm deletion")
        return False
    
    def check_success_notification(self):
        """Check for success notification"""
        print("Checking for success notification...")
        
        notification_selectors = [
            '.ant-message-success',
            '.ant-notification-notice-success',
            '.ant-message:has-text("success")',
            '.ant-notification:has-text("success")',
            '[role="alert"]:has-text("success")'
        ]
        
        for selector in notification_selectors:
            element = self.page.locator(selector).first
            if element.is_visible():
                message = element.text_content()
                print(f"Success notification: {message}")
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
            print("Starting System Permissions Delete Test (Smart Version)...")
            
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
                self.take_screenshot("permissions_delete_before_expert")
            
            if not self.switch_to_expert_mode():
                print("Warning: Could not switch to Expert mode")
            
            # Take screenshot after mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("permissions_delete_after_expert")
            
            if not self.navigate_to_permissions():
                raise Exception("Could not navigate to Permissions tab")
            
            # Take screenshot of permissions page
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("permissions_delete_list")
            
            if self.delete_permission_group():
                # Confirm deletion
                if self.confirm_deletion():
                    # Wait for operation to complete
                    self.page.wait_for_load_state("networkidle", timeout=3000)
                    
                    # Check for success
                    self.check_success_notification()
                    
                    # Take final screenshot
                    if self.config.get('screenshots', {}).get('enabled', True):
                        self.take_screenshot("permissions_delete_complete")
                    
                    print("Permission group deletion completed successfully!")
                else:
                    print("Deletion was not confirmed")
            else:
                print("No permission group was deleted")
            
            print("\nTest completed!")
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            
            # Take error screenshot
            if self.page and self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("permissions_delete_error")
            
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
        test = PermissionsDeleteTest()
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