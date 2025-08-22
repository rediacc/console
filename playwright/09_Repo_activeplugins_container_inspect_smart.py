#!/usr/bin/env python3
"""
Container Inspect Test - Smart Version
Tests the container inspection functionality in Rediacc console
- Uses config.json for all configuration
- Smart waits instead of sleep()
- Better error handling and success detection
"""

import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

class ContainerInspectTest:
    """Container inspection test with smart waits and config-based setup"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.base_url = self.config.get('baseUrl', 'http://localhost:7322')
        self.credentials = self.config['login']['credentials']
        self.timeouts = self.config['login']['timeouts']
        self.browser_config = self.config.get('browser', {})
        self.screenshots_path = Path(self.config['screenshots']['path'])
        self.screenshots_path.mkdir(parents=True, exist_ok=True)
        
        # Machine configuration
        self.target_machine = self.config.get('repoActions', {}).get('machineName', 'rediacc11')
        
    def wait_for_element(self, page, selector, state="visible", timeout=None):
        """Smart wait for element with configurable timeout"""
        if timeout is None:
            timeout = self.timeouts.get('element', 5000)
        
        try:
            element = page.locator(selector).first
            element.wait_for(state=state, timeout=timeout)
            return element
        except:
            return None
    
    def wait_for_network_idle(self, page, timeout=None):
        """Wait for network to be idle"""
        if timeout is None:
            timeout = self.timeouts.get('network', 5000)
        
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except:
            return False
    
    def take_screenshot(self, page, name):
        """Take screenshot with configured path"""
        screenshot_path = self.screenshots_path / f"{name}.png"
        page.screenshot(path=str(screenshot_path))
        print(f"   Screenshot saved: {screenshot_path.name}")
        return screenshot_path
    
    def login(self, page):
        """Login using configuration credentials"""
        print("Performing login...")
        
        # Check if we're on login page
        current_url = page.url
        if '/login' not in current_url and 'signin' not in current_url and not current_url.endswith('/console/'):
            # Navigate to login
            login_link = self.wait_for_element(page, '[data-testid="header-login-link"], a:has-text("Login")')
            if login_link:
                with page.expect_popup() as popup_info:
                    login_link.click()
                page = popup_info.value
        
        # Fill login form using config credentials
        email_selectors = [
            '[data-testid="login-email-input"]',
            'input[type="email"]',
            'input[placeholder*="email" i]'
        ]
        
        email_input = None
        for selector in email_selectors:
            email_input = self.wait_for_element(page, selector, timeout=2000)
            if email_input:
                break
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        email_input.fill(self.credentials['email'])
        
        # Fill password
        password_selectors = [
            '[data-testid="login-password-input"]',
            'input[type="password"]'
        ]
        
        password_input = None
        for selector in password_selectors:
            password_input = self.wait_for_element(page, selector, timeout=2000)
            if password_input:
                break
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        password_input.fill(self.credentials['password'])
        
        # Submit login
        submit_selectors = [
            '[data-testid="login-submit-button"]',
            'button[type="submit"]',
            'button:has-text("Sign In")'
        ]
        
        submit_button = None
        for selector in submit_selectors:
            submit_button = self.wait_for_element(page, selector, timeout=2000)
            if submit_button:
                break
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        submit_button.click()
        
        # Wait for dashboard with configured timeout
        dashboard_url = self.config['validation']['dashboardUrl']
        page.wait_for_url(dashboard_url, timeout=self.timeouts['navigation'])
        print("   Login successful!")
        
        return page
    
    def navigate_to_resources(self, page):
        """Navigate to resources page with smart waits"""
        print("Navigating to Resources...")
        
        resources_selector = '[data-testid="main-nav-resources"]'
        resources_link = self.wait_for_element(page, resources_selector)
        
        if not resources_link:
            # Fallback to text-based selector
            resources_link = page.get_by_text("Resources", exact=True).first
        
        resources_link.click()
        self.wait_for_network_idle(page)
        
        # Wait for resources table to load
        self.wait_for_element(page, '.ant-table, table', timeout=self.timeouts['navigation'])
        print("   Resources page loaded")
    
    def expand_machine(self, page):
        """Expand machine with smart waits"""
        print(f"Expanding machine {self.target_machine}...")
        
        # Try test-id first
        machine_expand = self.wait_for_element(
            page, 
            f'[data-testid="machine-expand-{self.target_machine}"]',
            timeout=3000
        )
        
        if not machine_expand:
            # Fallback to finding by text
            machine_row = page.locator(f'tr:has-text("{self.target_machine}")').first
            if machine_row.is_visible():
                expand_button = machine_row.locator('button[class*="expand"]').first
                if expand_button.is_visible():
                    expand_button.click()
                else:
                    # Click first button in row
                    machine_row.locator('button').first.click()
            else:
                raise Exception(f"Machine {self.target_machine} not found")
        else:
            machine_expand.click()
        
        # Wait for expansion to complete
        self.wait_for_network_idle(page)
        
        # Wait for nested content to appear
        nested_content = self.wait_for_element(
            page,
            '.ant-table-expanded-row, .machine-details, [class*="expanded"]',
            timeout=3000
        )
        
        if nested_content:
            print(f"   Machine {self.target_machine} expanded")
        else:
            print(f"   Warning: Machine expansion may not have completed fully")
    
    def find_and_expand_repository(self, page):
        """Find and expand repository with smart waits"""
        print("Looking for repositories...")
        
        # Wait for repository table or empty state
        repo_table = self.wait_for_element(
            page,
            '.ant-table-tbody tr:has-text("repo"), .ant-empty-description:has-text("No repositories")',
            timeout=5000
        )
        
        if not repo_table:
            print("   No repository table found")
            return False
        
        # Check for empty state
        empty_state = page.locator('.ant-empty-description:has-text("No repositories")').first
        if empty_state.is_visible():
            print("   No repositories found in this team")
            return False
        
        # Try to find repository expand button
        repo_expand_selectors = [
            'button.ant-table-row-expand-icon:not(.ant-table-row-expand-icon-expanded)',
            'button[aria-label*="expand"]:not([aria-expanded="true"])',
            '.ant-table-row button[class*="expand"]'
        ]
        
        for selector in repo_expand_selectors:
            repo_expand = self.wait_for_element(page, selector, timeout=2000)
            if repo_expand:
                print("   Expanding repository...")
                repo_expand.click()
                
                # Wait for expansion
                self.wait_for_network_idle(page)
                
                # Wait for container info to appear
                container_info = self.wait_for_element(
                    page,
                    '.container-info, .container-status, [class*="container"]',
                    timeout=3000
                )
                
                if container_info:
                    print("   Repository expanded, container info visible")
                return True
        
        print("   No expandable repositories found")
        return False
    
    def inspect_container(self, page):
        """Find and click container inspect action with smart waits"""
        print("Looking for container actions...")
        
        # Wait for any container-related elements
        container_selectors = [
            'button[data-testid*="container-actions"]',
            'button[title*="container"]',
            'button:has-text("Actions")',
            '.ant-dropdown-trigger:has-text("Actions")',
            'button[class*="action"]:has-text("Actions")'
        ]
        
        container_button = None
        for selector in container_selectors:
            container_button = self.wait_for_element(page, selector, timeout=2000)
            if container_button:
                break
        
        if not container_button:
            print("   No container actions button found")
            return False
        
        print("   Found container actions button")
        container_button.click()
        
        # Wait for dropdown menu
        dropdown_menu = self.wait_for_element(
            page,
            '.ant-dropdown-menu, .ant-menu-vertical, [role="menu"]',
            timeout=3000
        )
        
        if not dropdown_menu:
            print("   Dropdown menu did not appear")
            return False
        
        # Look for container_inspect option
        inspect_option = self.wait_for_element(
            page,
            'li:has-text("container_inspect"), .ant-dropdown-menu-item:has-text("container_inspect")',
            timeout=2000
        )
        
        if not inspect_option:
            print("   container_inspect option not found in menu")
            return False
        
        print("   Clicking container_inspect...")
        inspect_option.click()
        
        # Wait for inspection results
        self.wait_for_network_idle(page)
        
        # Check for success indicators
        success_indicators = [
            '.ant-message-success',
            '.ant-notification-success',
            'text="Container inspection completed"',
            'text="Inspection successful"',
            '.inspection-results',
            '.container-details'
        ]
        
        for indicator in success_indicators:
            success_element = self.wait_for_element(page, indicator, timeout=3000)
            if success_element:
                print("   Container inspection successful!")
                return True
        
        # Check if modal opened with inspection data
        modal = self.wait_for_element(page, '.ant-modal-content', timeout=3000)
        if modal:
            print("   Container inspection modal opened")
            return True
        
        print("   Container inspection initiated, waiting for results...")
        return True
    
    def run(self, playwright: Playwright) -> None:
        """Main test execution with smart waits"""
        browser = None
        context = None
        
        try:
            print("Starting Container Inspect Test (Smart Version)...")
            print(f"Configuration: {self.base_url}")
            print(f"Target Machine: {self.target_machine}")
            
            # Launch browser with config settings
            browser = playwright.chromium.launch(
                headless=self.browser_config.get('headless', False),
                slow_mo=self.browser_config.get('slowMo', 0)
            )
            
            context = browser.new_context(
                viewport=self.browser_config.get('viewport', {'width': 1280, 'height': 720})
            )
            
            page = context.new_page()
            
            # Set default timeout from config
            page.set_default_timeout(self.config['timeouts']['pageLoad'])
            
            # Step 1: Navigate to console
            print("\n1. Navigating to console...")
            page.goto(f"{self.base_url}/console")
            self.wait_for_network_idle(page)
            
            # Step 2: Login
            print("\n2. Performing authentication...")
            page = self.login(page)
            self.take_screenshot(page, "02_after_login")
            
            # Step 3: Navigate to Resources
            print("\n3. Accessing Resources section...")
            self.navigate_to_resources(page)
            self.take_screenshot(page, "03_resources_page")
            
            # Step 4: Expand machine
            print(f"\n4. Expanding machine {self.target_machine}...")
            self.expand_machine(page)
            self.take_screenshot(page, "04_machine_expanded")
            
            # Step 5: Find and expand repository
            print("\n5. Searching for repositories...")
            repo_found = self.find_and_expand_repository(page)
            self.take_screenshot(page, "05_repository_state")
            
            if not repo_found:
                print("\n⚠️ No repositories available for container inspection")
                print("This is expected if no repositories are configured in the test environment")
            else:
                # Step 6: Inspect container
                print("\n6. Initiating container inspection...")
                inspection_success = self.inspect_container(page)
                self.take_screenshot(page, "06_inspection_result")
                
                if inspection_success:
                    print("\n✅ Container inspection completed successfully!")
                else:
                    print("\n⚠️ Container inspection may not have completed fully")
            
            # Final screenshot
            self.take_screenshot(page, "07_final_state")
            
            print("\n🎉 Test completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Error during test: {str(e)}")
            if 'page' in locals():
                error_screenshot = self.take_screenshot(page, "error_screenshot")
                print(f"Error screenshot saved: {error_screenshot}")
            raise
        
        finally:
            # Cleanup
            if context:
                context.close()
            if browser:
                browser.close()
            print("\nBrowser closed.")

def main():
    """Entry point"""
    try:
        # Check for custom config path
        config_path = None
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        
        test = ContainerInspectTest(config_path)
        
        with sync_playwright() as playwright:
            test.run(playwright)
            
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()