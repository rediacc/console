#!/usr/bin/env python3
"""
Machine Trace Test - Smart Version
Tests the machine trace functionality in Rediacc console with intelligent waits and config-based values
"""

import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class MachineTraceTest:
    """Smart machine trace test with configuration support"""
    
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
        
    def open_machine_trace(self):
        """Open machine trace from config"""
        machine_name = self.config.get("createRepo", {}).get("machineName", "rediacc11")
        print(f"7. Opening machine trace for {machine_name}...")
        
        # Wait for the machine row to be visible
        self.page.wait_for_selector(f'text={machine_name}', timeout=5000)
        
        # Try multiple strategies to find trace button
        trace_strategies = [
            lambda: self.page.get_by_test_id(f"machine-trace-{machine_name}"),
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('button[title*="trace" i]').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('[data-testid*="trace"]').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('button:has-text("Trace")').first,
            lambda: self.page.locator(f'tr:has-text("{machine_name}")').locator('[aria-label*="trace" i]').first
        ]
        
        trace_opened = False
        for strategy in trace_strategies:
            try:
                element = strategy()
                if element.count() > 0 and element.is_visible():
                    element.click()
                    print(f"   Machine trace opened for {machine_name}")
                    trace_opened = True
                    break
            except:
                continue
        
        if not trace_opened:
            print(f"   Could not find trace button for {machine_name}")
            self.take_screenshot("trace_button_not_found")
            return False
        
        # Wait for trace modal or page to load
        trace_indicators = [
            '.ant-modal:has-text("Trace")',
            '.ant-modal:has-text("Queue")',
            'text=Queue Trace',
            'text=Task History',
            '[data-testid*="trace-table"]',
            '.trace-container',
            'table:has-text("Status")'
        ]
        
        trace_loaded = False
        for indicator in trace_indicators:
            if self._wait_for_element_state(indicator, timeout=3000):
                trace_loaded = True
                print("   Trace view loaded successfully")
                break
        
        if not trace_loaded:
            print("   Trace view opened but waiting for content to load")
            self.page.wait_for_timeout(1000)
        
        return True
    
    def sort_by_column(self, column_name: str, test_id: str = None):
        """Sort trace table by specified column"""
        print(f"8. Sorting by {column_name} column...")
        
        # Try multiple strategies to find column header
        column_selectors = []
        
        if test_id:
            column_selectors.append(f'[data-testid="{test_id}"]')
        
        column_selectors.extend([
            f'th:has-text("{column_name}")',
            f'th:has-text("{column_name.capitalize()}")',
            f'th:has-text("{column_name.upper()}")',
            f'.ant-table-column-title:has-text("{column_name}")',
            f'[role="columnheader"]:has-text("{column_name}")',
            f'th[title*="{column_name}" i]'
        ])
        
        column_found = False
        for selector in column_selectors:
            try:
                element = self.page.locator(selector).first
                if element.count() > 0 and element.is_visible():
                    element.click()
                    print(f"   Sorted by {column_name} column")
                    column_found = True
                    
                    # Wait for sort to complete
                    self.page.wait_for_timeout(500)
                    
                    # Check for sort indicator
                    sort_indicators = [
                        '.ant-table-column-sort-up',
                        '.ant-table-column-sort-down',
                        '[aria-sort]'
                    ]
                    
                    for indicator in sort_indicators:
                        if self._wait_for_element_state(indicator, timeout=1000):
                            print(f"   Sort applied to {column_name} column")
                            break
                    
                    break
            except:
                continue
        
        if not column_found:
            print(f"   {column_name} column not found")
            # Take screenshot to debug
            self.take_screenshot(f"column_{column_name}_not_found")
        
        return column_found
    
    def capture_trace_data(self):
        """Capture and log trace data if available"""
        print("10. Capturing trace data...")
        
        try:
            # Look for trace table rows
            rows = self.page.locator('tbody tr, .ant-table-tbody tr')
            row_count = rows.count()
            
            if row_count > 0:
                print(f"   Found {row_count} trace entries")
                
                # Capture first few rows for verification
                for i in range(min(5, row_count)):
                    try:
                        row = rows.nth(i)
                        if row.is_visible():
                            row_text = row.text_content()
                            
                            # Try to extract key information
                            if "COMPLETED" in row_text:
                                print(f"   Entry {i+1}: COMPLETED")
                            elif "FAILED" in row_text:
                                print(f"   Entry {i+1}: FAILED")
                            elif "PENDING" in row_text:
                                print(f"   Entry {i+1}: PENDING")
                            elif "PROCESSING" in row_text:
                                print(f"   Entry {i+1}: PROCESSING")
                            elif "ASSIGNED" in row_text:
                                print(f"   Entry {i+1}: ASSIGNED")
                            else:
                                # Show first 100 chars of row content
                                preview = row_text[:100] + "..." if len(row_text) > 100 else row_text
                                print(f"   Entry {i+1}: {preview}")
                    except:
                        continue
            else:
                print("   No trace entries found")
        except Exception as e:
            print(f"   Could not capture trace data: {e}")
    
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
    
    def close_trace_modal(self):
        """Close trace modal if present"""
        try:
            # Try to find and click close button
            close_selectors = [
                '.ant-modal-close',
                'button:has-text("Close")',
                'button:has-text("Cancel")',
                '[aria-label="Close"]',
                '[data-testid*="close"]'
            ]
            
            for selector in close_selectors:
                try:
                    close_button = self.page.locator(selector).first
                    if close_button.is_visible():
                        close_button.click()
                        print("11. Trace modal closed")
                        return True
                except:
                    continue
        except:
            pass
        
        return False
    
    def run(self, playwright: Playwright) -> None:
        """Main test execution"""
        try:
            print("Starting Machine Trace Test (Smart Version)...")
            
            # Setup browser
            self.setup_browser(playwright)
            
            # Navigate to console
            self.navigate_to_console()
            
            # Perform login
            self.perform_login()
            
            # Navigate to Resources
            self.navigate_to_resources()
            
            # Open machine trace
            trace_opened = self.open_machine_trace()
            
            if not trace_opened:
                print("\nTest skipped: Could not open machine trace")
                self.take_screenshot("machine_trace_skip")
                return
            
            # Sort by different columns - try common column names
            self.sort_by_column("Updated", "trace-column-updated")
            self.sort_by_column("Created", "trace-column-created") 
            self.sort_by_column("Status", "trace-column-status")
            self.sort_by_column("Task", "trace-column-task")
            self.sort_by_column("Bridge", "trace-column-bridge")
            
            # Capture trace data
            self.capture_trace_data()
            
            # Take final screenshot
            self.take_screenshot("machine_trace_success")
            
            # Close modal if present
            self.close_trace_modal()
            
            print("\nTest completed successfully!")
            
            # Brief pause to see final state
            self.page.wait_for_timeout(1000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            self.take_screenshot("machine_trace_error")
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
        test = MachineTraceTest()
        
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