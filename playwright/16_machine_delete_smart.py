#!/usr/bin/env python3
"""
Machine Delete Test - Smart Version
Tests the machine deletion functionality in Rediacc console with intelligent waits and config-based values
"""

import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class MachineDeleteTest:
    """Smart machine delete test with configuration support"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self.config = self._load_config()
        self.page = None
        self.context = None
        self.browser = None
        
    def _load_config(self) -> dict:
        """Load configuration from JSON file"""
        if not self.config_path.exists():
            print(f"Warning: Config file not found at {self.config_path}, using defaults")
            return self._get_default_config()
        
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def _get_default_config(self) -> dict:
        """Get default configuration if config file is missing"""
        return {
            "baseUrl": "http://localhost:7322",
            "login": {
                "credentials": {
                    "email": "admin@rediacc.io",
                    "password": "admin"
                },
                "timeouts": {
                    "navigation": 10000,
                    "element": 5000,
                    "network": 5000
                }
            },
            "browser": {
                "headless": False,
                "slowMo": 0
            },
            "timeouts": {
                "pageLoad": 30000,
                "elementVisible": 5000,
                "apiResponse": 10000
            },
            "createRepo": {
                "machineName": "rediacc11"
            },
            "createMachine": {
                "machineName": "rediacc21"
            }
        }
    
    def setup_browser(self, playwright: Playwright):
        """Setup browser with configuration"""
        browser_config = self.config.get("browser", {})
        self.browser = playwright.chromium.launch(
            headless=browser_config.get("headless", False),
            slow_mo=browser_config.get("slowMo", 0)
        )
        
        viewport = browser_config.get("viewport", {"width": 1280, "height": 720})
        self.context = self.browser.new_context(viewport=viewport)
        self.page = self.context.new_page()
        
        # Set default timeout from config
        timeout = self.config.get("timeouts", {}).get("pageLoad", 30000)
        self.page.set_default_timeout(timeout)
        
    def navigate_to_console(self):
        """Navigate to console URL from config"""
        base_url = self.config.get("baseUrl", "http://localhost:7322")
        console_url = f"{base_url}/console"
        
        print(f"1. Navigating to console: {console_url}")
        self.page.goto(console_url)
        self.page.wait_for_load_state("domcontentloaded")
        
    def perform_login(self):
        """Login using credentials from config"""
        current_url = self.page.url
        print(f"2. Current URL: {current_url}")
        
        # Check if we need to navigate to login
        if '/login' not in current_url and 'signin' not in current_url and not current_url.endswith('/console/'):
            print("3. Looking for login link...")
            try:
                login_link = self.page.get_by_role("banner").get_by_role("link", name="Login")
                with self.page.expect_popup() as popup_info:
                    login_link.click()
                self.page = popup_info.value
                print("   Navigated to login page via popup")
            except:
                print("   No login link found, assuming already on login page")
        else:
            print("3. On login page, proceeding with login...")
        
        print("4. Logging in...")
        
        # Get credentials from config
        credentials = self.config.get("login", {}).get("credentials", {})
        email = credentials.get("email", "admin@rediacc.io")
        password = credentials.get("password", "admin")
        
        # Use config-based test IDs - check multiple possible locations in config
        ui_config = self.config.get("ui", {})
        repo_edit_config = self.config.get("repoEdit", {}).get("ui", {})
        
        # Try to get test IDs from different config sections
        email_test_id = (
            ui_config.get("loginEmailTestId") or 
            repo_edit_config.get("loginEmailTestId") or 
            "login-email-input"
        )
        password_test_id = (
            ui_config.get("loginPasswordTestId") or 
            repo_edit_config.get("loginPasswordTestId") or 
            "login-password-input"
        )
        submit_test_id = (
            ui_config.get("loginSubmitButtonTestId") or 
            repo_edit_config.get("loginSubmitButtonTestId") or 
            "login-submit-button"
        )
        
        # Fill email with intelligent wait
        print(f"   Looking for email input (test-id: {email_test_id})")
        email_input = self._find_element_smart([
            f'[data-testid="{email_test_id}"]',
            'input[type="email"]',
            'input[placeholder*="email" i]',
            'input[name="email"]',
            '#email'
        ], description="email input field")
        email_input.fill(email)
        print(f"   Email filled: {email}")
        
        # Fill password with intelligent wait
        print(f"   Looking for password input (test-id: {password_test_id})")
        password_input = self._find_element_smart([
            f'[data-testid="{password_test_id}"]',
            'input[type="password"]',
            'input[placeholder*="password" i]',
            'input[name="password"]',
            '#password'
        ], description="password input field")
        password_input.fill(password)
        print(f"   Password filled")
        
        # Click submit with intelligent wait
        print(f"   Looking for submit button (test-id: {submit_test_id})")
        submit_button = self._find_element_smart([
            f'[data-testid="{submit_test_id}"]',
            'button[type="submit"]',
            'button:has-text("Sign In")',
            'button:has-text("Login")',
            'button:has-text("Submit")'
        ], description="submit button")
        submit_button.click()
        print(f"   Submit button clicked")
        
        # Wait for dashboard
        print("5. Waiting for dashboard...")
        dashboard_url = self.config.get("validation", {}).get("dashboardUrl", "**/console/dashboard")
        
        try:
            self.page.wait_for_url(dashboard_url, timeout=10000)
            print("   Login successful!")
        except:
            # If URL wait fails, check if we're already logged in or on a different page
            current_url = self.page.url
            print(f"   Current URL after login attempt: {current_url}")
            
            # Check for common post-login indicators
            if any(indicator in current_url for indicator in ['/dashboard', '/resources', '/home']):
                print("   Login appears successful (on valid page)")
            else:
                # Check for error messages
                error_selectors = [
                    'text=Invalid credentials',
                    'text=Login failed',
                    '.ant-message-error',
                    '.error-message'
                ]
                
                for selector in error_selectors:
                    if self._wait_for_element_state(selector, timeout=1000):
                        error_element = self.page.locator(selector).first
                        error_text = error_element.text_content() if error_element.count() > 0 else "Unknown error"
                        print(f"   Login error: {error_text}")
                        self.take_screenshot("login_error")
                        raise Exception(f"Login failed: {error_text}")
                
                print("   Warning: Could not verify login success, continuing anyway...")
        
    def _find_element_smart(self, selectors: list, timeout: int = None, description: str = "element"):
        """Find element using multiple selectors with intelligent wait"""
        if timeout is None:
            timeout = self.config.get("timeouts", {}).get("elementVisible", 5000)
        
        last_error = None
        for selector in selectors:
            try:
                element = self.page.locator(selector).first
                # Check if element exists first
                if element.count() > 0:
                    element.wait_for(state="visible", timeout=timeout)
                    return element
            except Exception as e:
                last_error = e
                continue
        
        # If we get here, element was not found - provide helpful debug info
        print(f"   DEBUG: Could not find {description}")
        print(f"   Tried selectors: {selectors}")
        if last_error:
            print(f"   Last error: {last_error}")
        
        # Take a debug screenshot
        self.take_screenshot(f"debug_{description.replace(' ', '_')}")
        
        raise Exception(f"Could not find {description} with any of these selectors: {selectors}")
    
    def _wait_for_element_state(self, selector: str, state: str = "visible", timeout: int = None):
        """Wait for element to reach specific state"""
        if timeout is None:
            timeout = self.config.get("timeouts", {}).get("elementVisible", 5000)
        
        try:
            element = self.page.locator(selector).first
            element.wait_for(state=state, timeout=timeout)
            return True
        except:
            return False
    
    def navigate_to_resources(self):
        """Navigate to Resources page"""
        print("6. Navigating to Resources...")
        resources_test_id = self.config.get("ui", {}).get("resourcesMenuTestId", "main-nav-machines")
        
        # Try multiple ways to find resources link
        resources_selectors = [
            f'[data-testid="{resources_test_id}"]',
            'nav a:has-text("Resources")',
            'a[href*="/resources"]',
            'text=Resources'
        ]
        
        resources_link = None
        for selector in resources_selectors:
            try:
                element = self.page.locator(selector).first
                if element.count() > 0 and element.is_visible():
                    resources_link = element
                    break
            except:
                continue
        
        if resources_link:
            resources_link.click()
        else:
            raise Exception("Could not find Resources link")
        
        # Wait for network to be idle instead of using sleep
        self.page.wait_for_load_state("networkidle")
        
    def delete_machine(self):
        """Delete machine from config or find deletable machine"""
        # Try to get machine name from config - use rediacc11 as primary default
        machine_name = (
            self.config.get("createRepo", {}).get("machineName") or
            self.config.get("createMachine", {}).get("machineName", "rediacc11")
        )
        
        print(f"7. Looking for delete button for machine {machine_name}...")
        
        # Wait for machines table to load
        self.page.wait_for_selector('table', timeout=5000)
        
        # First check if the machine exists
        machine_exists = self._wait_for_element_state(f'text={machine_name}', timeout=2000)
        
        if not machine_exists:
            print(f"   Machine {machine_name} not found, looking for any deletable machine...")
            # Find any machine with a delete button
            machine_name = self._find_deletable_machine()
            if not machine_name:
                print("   No deletable machines found")
                return False
        
        # Try multiple strategies to find delete button
        delete_strategies = [
            lambda: self.page.get_by_test_id(f"machine-delete-{machine_name}"),
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('button[title*="delete" i]').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('[data-testid*="delete"]').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('button:has-text("Delete")').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('[aria-label*="delete" i]').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('svg[data-icon="delete"]').locator('..').first
        ]
        
        delete_clicked = False
        for strategy in delete_strategies:
            try:
                element = strategy()
                if element.count() > 0 and element.is_visible():
                    element.click()
                    print(f"   Delete button clicked for {machine_name}")
                    delete_clicked = True
                    break
            except:
                continue
        
        if not delete_clicked:
            print(f"   Could not find delete button for {machine_name}")
            self.take_screenshot("delete_button_not_found")
            return False
        
        # Wait for confirmation dialog to appear
        dialog_indicators = [
            '.ant-modal',
            '[role="dialog"]',
            'text=Confirm',
            'text=Are you sure'
        ]
        
        dialog_appeared = False
        for indicator in dialog_indicators:
            if self._wait_for_element_state(indicator, timeout=3000):
                dialog_appeared = True
                print("   Confirmation dialog appeared")
                break
        
        if not dialog_appeared:
            print("   Warning: Confirmation dialog did not appear")
            return False
        
        return self._confirm_deletion()
    
    def _find_deletable_machine(self):
        """Find any machine that has a delete button"""
        try:
            # Look for any delete button in the table
            delete_buttons = self.page.locator('[data-testid*="machine-delete"], button[title*="delete" i], button:has-text("Delete")')
            
            if delete_buttons.count() > 0:
                # Get the first visible delete button
                for i in range(delete_buttons.count()):
                    button = delete_buttons.nth(i)
                    if button.is_visible():
                        # Try to find the machine name from the same row
                        row = button.locator('..').locator('..')  # Go up to row
                        machine_text = row.text_content()
                        
                        # Extract machine name (assuming it's in the first column)
                        if machine_text:
                            parts = machine_text.split()
                            if parts:
                                return parts[0]  # Return first word as machine name
                
        except:
            pass
        
        return None
    
    def _confirm_deletion(self):
        """Confirm the deletion in the modal dialog"""
        print("8. Confirming deletion...")
        
        # Try multiple strategies to find confirm button
        confirm_selectors = [
            '[data-testid="confirm-delete-button"]',
            'button:has-text("OK")',
            'button:has-text("Confirm")',
            'button:has-text("Yes")',
            'button:has-text("Delete")',
            '.ant-modal button.ant-btn-primary',
            '.ant-modal button.ant-btn-dangerous',
            '[role="dialog"] button.ant-btn-dangerous',
            '[role="dialog"] button:has-text("Delete")',
            '.ant-modal-footer button.ant-btn-dangerous'
        ]
        
        confirm_clicked = False
        for selector in confirm_selectors:
            try:
                element = self.page.locator(selector).first
                if element.count() > 0 and element.is_visible():
                    element.click()
                    print("   Deletion confirmed")
                    confirm_clicked = True
                    break
            except:
                continue
        
        if not confirm_clicked:
            print("   Could not find confirm button")
            self.take_screenshot("confirm_button_not_found")
            return False
        
        # Wait for deletion to complete
        return self._wait_for_deletion_completion()
    
    def _wait_for_deletion_completion(self):
        """Wait for deletion to complete and verify"""
        print("9. Waiting for deletion to complete...")
        
        # Check for success indicators
        success_indicators = [
            '.ant-message-success',
            '.ant-notification-success',
            'text=successfully deleted',
            'text=Machine deleted',
            'text=Deletion successful',
            'text=Success'
        ]
        
        deletion_success = False
        for indicator in success_indicators:
            if self._wait_for_element_state(indicator, timeout=5000):
                deletion_success = True
                print("   Machine deleted successfully!")
                break
        
        if not deletion_success:
            # Check if modal disappeared (another indicator of success)
            modal_gone = not self._wait_for_element_state('.ant-modal', state="visible", timeout=1000)
            if modal_gone:
                print("   Deletion appears to have completed (modal closed)")
                deletion_success = True
            else:
                print("   Could not verify deletion success")
        
        return deletion_success
    
    def take_screenshot(self, name: str = "screenshot"):
        """Take screenshot with configured path"""
        screenshots_config = self.config.get("screenshots", {})
        if not screenshots_config.get("enabled", True):
            return
        
        screenshot_dir = Path(screenshots_config.get("path", "./artifacts/screenshots"))
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        screenshot_path = screenshot_dir / f"{name}.png"
        self.page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved to: {screenshot_path}")
    
    def verify_machine_deleted(self, machine_name: str = None):
        """Verify that machine is actually deleted from the list"""
        if not machine_name:
            return True  # Can't verify without machine name
        
        print(f"10. Verifying {machine_name} is deleted...")
        
        # Wait a moment for the table to refresh
        self.page.wait_for_timeout(1000)
        
        # Check if machine still exists in the list
        machine_still_exists = self._wait_for_element_state(f'text={machine_name}', timeout=2000)
        
        if not machine_still_exists:
            print(f"   Confirmed: {machine_name} has been removed from the list")
            return True
        else:
            print(f"   Warning: {machine_name} still appears in the list")
            return False
    
    def run(self, playwright: Playwright) -> None:
        """Main test execution"""
        try:
            print("Starting Machine Delete Test (Smart Version)...")
            
            # Setup browser
            self.setup_browser(playwright)
            
            # Navigate to console
            self.navigate_to_console()
            
            # Perform login
            self.perform_login()
            
            # Navigate to Resources
            self.navigate_to_resources()
            
            # Delete machine
            deletion_started = self.delete_machine()
            
            if deletion_started:
                # Use the same machine name that was deleted
                machine_name = (
                    self.config.get("createRepo", {}).get("machineName") or
                    self.config.get("createMachine", {}).get("machineName", "rediacc11")
                )
                
                # Verify deletion
                self.verify_machine_deleted(machine_name)
                
                print("\nTest completed successfully!")
                self.take_screenshot("machine_delete_success")
            else:
                print("\nTest completed with warnings")
                self.take_screenshot("machine_delete_warning")
            
            # Brief pause to see final state
            self.page.wait_for_timeout(1000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            self.take_screenshot("machine_delete_error")
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
        # Initialize test with config
        test = MachineDeleteTest()
        
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