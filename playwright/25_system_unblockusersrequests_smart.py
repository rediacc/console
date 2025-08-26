#!/usr/bin/env python3
"""
System Unblock User Requests Test - Smart Version
Tests the unblock user requests functionality in Rediacc console
"""

import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class UnblockUserRequestsTest:
    """Smart unblock user requests test with config-based approach"""
    
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
    
    def toggle_main_mode(self):
        """Toggle the main mode switch first (as per test flow)"""
        print("Toggling main mode...")
        
        mode_selectors = [
            '[data-testid="main-mode-toggle"]',
            '[data-testid*="mode-toggle"]',
            '.ant-switch',
            'button.ant-switch',
            '[role="switch"]',
            'button[data-testid*="mode"]'
        ]
        
        for selector in mode_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for UI to update
                self.page.wait_for_timeout(500)
                print("Main mode toggled")
                return True
        
        print("Could not find mode toggle")
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
        
        # Check if Danger Zone is already visible (indicates Expert mode)
        danger_zone_visible = self.page.locator('text="Danger Zone"').is_visible() or \
                             self.page.locator('.danger-zone').is_visible()
        
        if danger_zone_visible:
            print("Danger Zone already visible (Expert mode active)")
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
    
    def unblock_user_requests(self):
        """Click the unblock user requests button"""
        print("Looking for unblock user requests button...")
        
        # Try various selectors for the unblock button
        unblock_selectors = [
            'button:has([aria-label*="unlock"])',
            'button:has(svg[data-icon="unlock"])',
            'button:has-text("Unblock User Requests")',
            'button:has-text("Unblock Users")',
            '[data-testid*="unblock-user"]',
            '[data-testid*="unblock-requests"]',
            'button[title*="unblock" i]',
            'button:has-text("unlock")',
            '[role="button"]:has-text("Unblock")',
            '.danger-zone button:has([aria-label*="unlock"])'
        ]
        
        for selector in unblock_selectors:
            try:
                button = self.page.locator(selector).first
                if button.is_visible():
                    button.click()
                    print("Unblock user requests button clicked")
                    return True
            except:
                continue
        
        # Try to find by role with name
        try:
            button = self.page.get_by_role("button", name="unlock Unblock User Requests")
            if button.is_visible():
                button.click()
                print("Unblock user requests button clicked (by role)")
                return True
        except:
            pass
        
        print("Could not find unblock user requests button")
        return False
    
    def confirm_unblocking(self):
        """Confirm the unblocking action in dialog"""
        print("Confirming unblock user requests...")
        
        # Wait a moment for dialog to appear
        self.page.wait_for_timeout(500)
        
        # Look for the confirmation dialog
        confirm_selectors = [
            'button:has-text("Unblock User Requests")',
            'button:has-text("Yes, Unblock")',
            'button:has-text("Unblock")',
            'button:has-text("Yes")',
            'button:has-text("Confirm")',
            '.ant-modal button.ant-btn-primary',
            '.ant-modal button:has-text("Unblock")',
            '[role="dialog"] button:has-text("Unblock")',
            '[role="dialog"] button:has-text("Yes")',
            '.ant-notification button:has-text("Unblock")',
            '[data-testid*="confirm"]'
        ]
        
        for selector in confirm_selectors:
            if self.smart_click(selector, timeout=2000):
                print("Unblock user requests confirmed")
                return True
        
        # Try by role
        try:
            button = self.page.get_by_role("button", name="Yes, Unblock")
            if button.is_visible():
                button.click()
                print("Unblock user requests confirmed (by role)")
                return True
        except:
            pass
        
        print("Could not confirm unblocking")
        return False
    
    def check_success_notification(self):
        """Check for success notification"""
        print("Checking for success notification...")
        
        notification_selectors = [
            '.ant-message-success',
            '.ant-notification-notice-success',
            '.ant-message:has-text("unblocked")',
            '.ant-notification:has-text("unblocked")',
            '[role="alert"]:has-text("unblocked")',
            '.ant-message:has-text("success")',
            '.ant-notification:has-text("success")',
            'text="User requests unblocked successfully"'
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
            print("Starting System Unblock User Requests Test (Smart Version)...")
            
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
            
            # Toggle main mode first (as per original test flow)
            self.toggle_main_mode()
            
            if not self.navigate_to_system():
                raise Exception("Could not navigate to System")
            
            # Take screenshot before mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("unblockusers_before_expert")
            
            if not self.switch_to_expert_mode():
                print("Warning: Could not switch to Expert mode, continuing...")
            
            # Take screenshot after mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("unblockusers_after_expert")
            
            # Unblock user requests
            if self.unblock_user_requests():
                # Confirm unblocking
                if self.confirm_unblocking():
                    # Wait for operation to complete
                    self.page.wait_for_load_state("networkidle", timeout=3000)
                    
                    # Check for success
                    self.check_success_notification()
                    
                    # Take final screenshot
                    if self.config.get('screenshots', {}).get('enabled', True):
                        self.take_screenshot("unblockusers_complete")
                    
                    print("User requests unblocking completed successfully!")
                else:
                    print("Unblocking was not confirmed")
            else:
                print("Could not initiate user request unblocking")
            
            print("\nTest completed!")
            
            # Keep browser open briefly to observe results
            self.page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            
            # Take error screenshot
            if self.page and self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("unblockusers_error")
            
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
        test = UnblockUserRequestsTest()
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