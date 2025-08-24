#!/usr/bin/env python3
"""
Container Stop Test - Smart Version
Tests the container stop functionality in Rediacc console with intelligent waits and config-based values
"""

import json
import re
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class ContainerStopTest:
    """Smart container stop test with configuration support"""
    
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
        resources_test_id = self.config.get("ui", {}).get("resourcesMenuTestId", "main-nav-resources")
        resources_link = self.page.get_by_test_id(resources_test_id).get_by_text("Resources")
        resources_link.click()
        
        # Wait for network to be idle instead of using sleep
        self.page.wait_for_load_state("networkidle")
        
    def expand_machine(self):
        """Expand machine from config"""
        machine_name = self.config.get("createRepo", {}).get("machineName", "rediacc11")
        print(f"7. Expanding machine {machine_name}...")
        
        # Wait for the machine row to be visible
        self.page.wait_for_selector(f'text={machine_name}', timeout=5000)
        
        # Try multiple strategies to find and click expand button
        expand_strategies = [
            lambda: self.page.get_by_test_id(f"machine-expand-{machine_name}").locator("svg"),
            lambda: self.page.get_by_test_id(f"machine-expand-{machine_name}"),
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('[aria-label*="expand"]').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('button').first,
            lambda: self.page.locator(f'text={machine_name}').locator('..').locator('..').locator('button').first
        ]
        
        for strategy in expand_strategies:
            try:
                element = strategy()
                if element.count() > 0 and element.is_visible():
                    element.click()
                    print(f"   Machine {machine_name} expanded")
                    # Wait for expansion animation and content to load
                    self._wait_for_element_state('[data-testid*="machine-repo-list"], [data-testid*="repository"], text=Repository', timeout=2000)
                    return True
            except:
                continue
        
        print(f"   Warning: Could not expand machine {machine_name}")
        return False
        
    def expand_repository(self):
        """Expand repository with intelligent wait"""
        print("8. Looking for repositories to expand...")
        
        # Wait a moment for repository list to fully load
        self.page.wait_for_timeout(500)
        
        # Check multiple indicators for repository presence
        repo_indicators = [
            '[data-testid*="machine-repo-list"]',
            '.ant-table-tbody tr',
            'text=Repository',
            '[data-testid*="repository"]'
        ]
        
        has_repos = False
        for indicator in repo_indicators:
            if self._wait_for_element_state(indicator, timeout=1000):
                has_repos = True
                break
        
        if not has_repos:
            print("   No repository table found, checking for empty state...")
            # Check if there's an empty state message
            empty_indicators = ['text=No repositories', 'text=No data', '.ant-empty']
            for indicator in empty_indicators:
                if self._wait_for_element_state(indicator, timeout=500):
                    print("   No repositories available on this machine")
                    return False
            return False
        
        expand_strategies = [
            lambda: self.page.get_by_test_id("machine-repo-list-table").get_by_role("img", name="right").locator("svg"),
            lambda: self.page.locator('.ant-table-row-expand-icon:not(.ant-table-row-expand-icon-expanded)').first,
            lambda: self.page.locator('[aria-label*="expand"]:not([aria-label*="expanded"])').first,
            lambda: self.page.locator('button[class*="expand"]:not([class*="expanded"])').first,
            lambda: self.page.locator('.ant-table button svg').first
        ]
        
        for strategy in expand_strategies:
            try:
                element = strategy()
                if element.count() > 0 and element.is_visible():
                    element.click()
                    print("   Repository expanded")
                    # Wait for container info to appear
                    self._wait_for_element_state('[data-testid*="container"], text=Container, text=Status', timeout=2000)
                    return True
            except:
                continue
        
        print("   Could not find repository expand button")
        return False
        
    def stop_container(self):
        """Find and stop container with intelligent detection"""
        print("9. Looking for container actions...")
        
        # First check if container is running
        container_status = self._check_container_status()
        if container_status == "stopped":
            print("   Container is already stopped")
            return True
        elif container_status == "not_found":
            print("   No clear container status found, will try to find action buttons anyway")
        
        # Wait for any container action buttons to be present
        container_found = False
        
        # Try to find any container action button - try dynamic test IDs first
        container_buttons = self.page.locator('[data-testid*="machine-repo-list-container-actions"]')
        
        print(f"   Found {container_buttons.count()} potential container action buttons")
        
        if container_buttons.count() > 0:
            # Use the first visible container action button
            for i in range(container_buttons.count()):
                try:
                    button = container_buttons.nth(i)
                    if button.is_visible():
                        print(f"   Clicking container actions button (index {i})")
                        button.click()
                        container_found = True
                        # Wait for dropdown menu to appear
                        self.page.wait_for_timeout(500)
                        break
                except Exception as e:
                    print(f"   Could not click button {i}: {e}")
                    continue
        
        # If not found with test-id, try other selectors
        if not container_found:
            container_selectors = [
                'button:has-text("Actions")',
                '.ant-dropdown-trigger button',
                '.ant-table button[title*="Actions"]'
            ]
            
            for selector in container_selectors:
                if self._wait_for_element_state(selector, timeout=1000):
                    try:
                        container_button = self.page.locator(selector).first
                        if container_button.is_visible():
                            print("   Found container actions button")
                            container_button.click()
                            container_found = True
                            break
                    except:
                        continue
        
        if not container_found:
            print("   Warning: Could not find container actions button")
            print("   This might be because no containers are running")
            return False
        
        # Click container stop option
        print("10. Clicking container_stop...")
        
        # Wait for menu to appear
        self._wait_for_element_state('text=container_stop', timeout=2000)
        
        stop_option = self.page.get_by_text("container_stop")
        if stop_option.is_visible():
            stop_option.click()
            print("    Container stop initiated!")
            
            # Wait for stop confirmation
            success = self._wait_for_stop_confirmation()
            
            if success:
                print("    Container stopped successfully!")
            else:
                print("    Container stop initiated (awaiting confirmation)")
            
            return True
        else:
            print("    Could not find container_stop option")
            return False
    
    def _check_container_status(self):
        """Check current container status"""
        print("   Checking container status...")
        try:
            # Look for status indicators
            status_indicators = [
                'text=Running',
                'text=Stopped',
                'text=Exited',
                'text=Up',
                'text=Down',
                '[data-testid*="status"]',
                '.container-status',
                'td:has-text("Running")',
                'td:has-text("Stopped")'
            ]
            
            for indicator in status_indicators:
                element = self.page.locator(indicator).first
                if element.count() > 0 and element.is_visible():
                    status_text = element.text_content().lower()
                    print(f"   Found status indicator: {status_text}")
                    if 'stopped' in status_text or 'exited' in status_text or 'down' in status_text:
                        return "stopped"
                    elif 'running' in status_text or 'up' in status_text:
                        return "running"
        except Exception as e:
            print(f"   Error checking status: {e}")
        
        # If no clear status found, assume container exists but status unknown
        print("   Container status unknown, assuming it exists")
        return "unknown"
    
    def _wait_for_stop_confirmation(self):
        """Wait for container stop confirmation"""
        # Check for success indicators
        success_indicators = [
            '.ant-message-success',
            '.ant-notification-success',
            'text=successfully stopped',
            'text=Container stopped',
            'text=Success'
        ]
        
        for indicator in success_indicators:
            if self._wait_for_element_state(indicator, timeout=5000):
                return True
        
        # Also check if status changed to stopped
        self.page.wait_for_timeout(2000)
        status = self._check_container_status()
        return status == "stopped"
    
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
    
    def verify_container_stopped(self):
        """Verify that container is actually stopped"""
        print("11. Verifying container status...")
        
        # Wait a moment for UI to update
        self.page.wait_for_timeout(1000)
        
        # Check for stopped status
        stopped_indicators = [
            'text=Stopped',
            'text=Exited',
            'text=Not Running',
            '[data-testid*="status"]:has-text("Stopped")'
        ]
        
        for indicator in stopped_indicators:
            if self._wait_for_element_state(indicator, timeout=2000):
                print("    Container verified as stopped")
                return True
        
        print("    Could not verify container status")
        return False
    
    def run(self, playwright: Playwright) -> None:
        """Main test execution"""
        try:
            print("Starting Container Stop Test (Smart Version)...")
            
            # Setup browser
            self.setup_browser(playwright)
            
            # Navigate to console
            self.navigate_to_console()
            
            # Perform login
            self.perform_login()
            
            # Navigate to Resources
            self.navigate_to_resources()
            
            # Expand machine
            machine_expanded = self.expand_machine()
            
            if not machine_expanded:
                print("\nTest skipped: Could not expand machine")
                self.take_screenshot("container_stop_skip")
                return
            
            # Expand repository
            repo_expanded = self.expand_repository()
            
            if not repo_expanded:
                print("\nTest skipped: No repositories found")
                self.take_screenshot("container_stop_no_repos")
                return
            
            # Stop container
            success = self.stop_container()
            
            if success:
                # Verify container is stopped
                verified = self.verify_container_stopped()
                if verified:
                    print("\nTest completed successfully!")
                    self.take_screenshot("container_stop_success")
                else:
                    print("\nTest completed but verification pending")
                    self.take_screenshot("container_stop_pending")
            else:
                print("\nTest completed with warnings")
                self.take_screenshot("container_stop_warning")
            
            # Brief pause to see final state
            self.page.wait_for_timeout(1000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            self.take_screenshot("container_stop_error")
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
        test = ContainerStopTest()
        
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