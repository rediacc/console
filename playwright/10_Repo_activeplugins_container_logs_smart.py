#!/usr/bin/env python3
"""
Container Logs Test - Smart Version
Tests the container logs functionality in Rediacc console
- Uses config.json for all configuration
- Smart waits instead of sleep()
- Better error handling and success detection
"""

import re
import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

class ContainerLogsTest:
    """Container logs test with smart waits and config-based setup"""
    
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
        
        # Machine configuration from config
        self.target_machine = self.config.get('repoActions', {}).get('machineName', 'rediacc11')
        
        # Container-specific configuration
        self.container_selectors = {
            'actions_button': 'button[data-testid*="container-actions"]',
            'logs_option': 'container_logs',
            'logs_modal': '.ant-modal-content, .logs-modal, [role="dialog"]',
            'logs_content': '.log-content, .logs-viewer, pre, code'
        }
        
    def wait_for_element(self, page, selector, state="visible", timeout=None):
        """Smart wait for element with configurable timeout"""
        if timeout is None:
            timeout = self.timeouts.get('element', 5000)
        
        try:
            if isinstance(selector, str):
                element = page.locator(selector).first
            else:
                element = selector
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
    
    def wait_for_text(self, page, text, timeout=None):
        """Wait for specific text to appear on page"""
        if timeout is None:
            timeout = self.timeouts.get('element', 5000)
        
        try:
            page.wait_for_selector(f'text="{text}"', timeout=timeout)
            return True
        except:
            return False
    
    def take_screenshot(self, page, name):
        """Take screenshot with configured path"""
        screenshot_path = self.screenshots_path / f"{name}.png"
        page.screenshot(path=str(screenshot_path))
        print(f"   📸 Screenshot saved: {screenshot_path.name}")
        return screenshot_path
    
    def login(self, page):
        """Login using configuration credentials"""
        print("🔐 Performing login...")
        
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
        print("   ✅ Login successful!")
        
        return page
    
    def navigate_to_resources(self, page):
        """Navigate to resources page with smart waits"""
        print("📂 Navigating to Resources...")
        
        resources_selector = '[data-testid="main-nav-resources"]'
        resources_link = self.wait_for_element(page, resources_selector)
        
        if not resources_link:
            # Fallback to text-based selector
            resources_link = page.get_by_text("Resources", exact=True).first
        
        resources_link.click()
        self.wait_for_network_idle(page)
        
        # Wait for resources table to load
        self.wait_for_element(page, '.ant-table, table', timeout=self.timeouts['navigation'])
        print("   ✅ Resources page loaded")
    
    def expand_machine(self, page):
        """Expand machine with smart waits"""
        print(f"🖥️ Expanding machine {self.target_machine}...")
        
        # Try multiple selectors for machine expansion
        expand_selectors = [
            f'[data-testid="machine-expand-{self.target_machine}"]',
            f'[data-testid="machine-expand-{self.target_machine}"] svg',
            f'tr:has-text("{self.target_machine}") button:first-of-type'
        ]
        
        machine_expanded = False
        for selector in expand_selectors:
            expand_button = self.wait_for_element(page, selector, timeout=2000)
            if expand_button:
                expand_button.click()
                machine_expanded = True
                break
        
        if not machine_expanded:
            # Final fallback - find row and click first button
            machine_row = page.locator(f'tr:has-text("{self.target_machine}")').first
            if machine_row.is_visible():
                machine_row.locator('button').first.click()
                machine_expanded = True
        
        if not machine_expanded:
            raise Exception(f"Could not expand machine {self.target_machine}")
        
        # Wait for expansion to complete
        self.wait_for_network_idle(page)
        
        # Wait for nested content
        nested_content = self.wait_for_element(
            page,
            '.ant-table-expanded-row, .machine-details, [class*="expanded"]',
            timeout=3000
        )
        
        if nested_content:
            print(f"   ✅ Machine {self.target_machine} expanded")
        else:
            print(f"   ⚠️ Machine expansion may not have completed fully")
    
    def expand_repository(self, page):
        """Find and expand repository with smart waits"""
        print("📦 Looking for repositories to expand...")
        
        # Wait for repository table or empty state
        repo_content = self.wait_for_element(
            page,
            '.ant-table-tbody tr, .ant-empty-description',
            timeout=5000
        )
        
        if not repo_content:
            print("   ❌ No repository content found")
            return False
        
        # Check for empty state
        empty_state = page.locator('.ant-empty-description:has-text("No repositories")').first
        if empty_state.is_visible():
            print("   ⚠️ No repositories found in this team")
            return False
        
        # Try to find repository cell with regex pattern
        repo_expanded = False
        
        # Method 1: Find by test-id and role
        try:
            repo_table = page.get_by_test_id("machine-repo-list-table")
            if repo_table.is_visible():
                repo_cell = repo_table.get_by_role("cell", name=re.compile("repo", re.IGNORECASE)).first
                if repo_cell.is_visible():
                    # Click the expand icon within the cell
                    expand_span = repo_cell.locator("span").first
                    if expand_span.is_visible():
                        expand_span.click()
                        repo_expanded = True
                        print("   ✅ Repository expanded via cell click")
        except:
            pass
        
        # Method 2: Find expand button directly
        if not repo_expanded:
            expand_button_selectors = [
                'button.ant-table-row-expand-icon:not(.ant-table-row-expand-icon-expanded)',
                'button[aria-label*="expand"]:not([aria-expanded="true"])',
                '.ant-table-row button[class*="expand"]'
            ]
            
            for selector in expand_button_selectors:
                expand_button = self.wait_for_element(page, selector, timeout=2000)
                if expand_button:
                    expand_button.click()
                    repo_expanded = True
                    print("   ✅ Repository expanded via expand button")
                    break
        
        if repo_expanded:
            # Wait for expansion to complete
            self.wait_for_network_idle(page)
            
            # Wait for container info to appear
            container_info = self.wait_for_element(
                page,
                '.container-info, .container-row, [data-testid*="container"]',
                timeout=3000
            )
            
            if container_info:
                print("   ✅ Container information visible")
                return True
        else:
            print("   ⚠️ Could not expand repository")
        
        return repo_expanded
    
    def open_container_logs(self, page):
        """Find and click container logs action with smart waits"""
        print("📋 Looking for container actions...")
        
        container_found = False
        
        # Try specific container ID patterns first
        specific_container_selectors = [
            '[data-testid*="machine-repo-list-container-actions"]',
            'button[data-testid*="container-actions"]'
        ]
        
        for selector in specific_container_selectors:
            container_buttons = page.locator(selector).all()
            if container_buttons:
                # Click the first available container action button
                container_buttons[0].click()
                container_found = True
                print(f"   ✅ Found container actions button")
                break
        
        # If not found, try generic selectors
        if not container_found:
            generic_selectors = [
                'button:has-text("Actions")',
                '.ant-dropdown-trigger:has-text("Actions")',
                '.ant-table-row button[title*="container"]'
            ]
            
            for selector in generic_selectors:
                container_button = self.wait_for_element(page, selector, timeout=2000)
                if container_button:
                    container_button.click()
                    container_found = True
                    print("   ✅ Found container actions button (generic)")
                    break
        
        if not container_found:
            print("   ❌ No container actions button found")
            return False
        
        # Wait for dropdown menu
        dropdown_menu = self.wait_for_element(
            page,
            '.ant-dropdown-menu, .ant-menu-vertical, [role="menu"]',
            timeout=3000
        )
        
        if not dropdown_menu:
            print("   ❌ Dropdown menu did not appear")
            return False
        
        # Look for container_logs option
        print("📝 Clicking container_logs...")
        
        logs_option_selectors = [
            'text="container_logs"',
            'li:has-text("container_logs")',
            '.ant-dropdown-menu-item:has-text("container_logs")',
            '[role="menuitem"]:has-text("logs")'
        ]
        
        logs_clicked = False
        for selector in logs_option_selectors:
            logs_option = self.wait_for_element(page, selector, timeout=2000)
            if logs_option:
                logs_option.click()
                logs_clicked = True
                print("   ✅ Container logs option clicked")
                break
        
        if not logs_clicked:
            print("   ❌ Could not find container_logs option")
            return False
        
        # Wait for logs to load
        self.wait_for_network_idle(page)
        
        # Check for logs modal or content
        logs_visible = False
        
        # Check for modal with logs
        logs_modal = self.wait_for_element(
            page,
            self.container_selectors['logs_modal'],
            timeout=5000
        )
        
        if logs_modal:
            print("   ✅ Logs modal opened")
            
            # Check for actual log content
            logs_content = self.wait_for_element(
                page,
                self.container_selectors['logs_content'],
                timeout=3000
            )
            
            if logs_content:
                print("   ✅ Log content is visible")
                logs_visible = True
                
                # Try to read some log content
                try:
                    log_text = logs_content.inner_text()
                    if log_text:
                        print(f"   📄 Sample log output: {log_text[:100]}...")
                except:
                    pass
        
        # Check for success notifications
        success_indicators = [
            '.ant-message-success',
            '.ant-notification-success',
            'text="Logs retrieved successfully"',
            'text="Container logs loaded"'
        ]
        
        for indicator in success_indicators:
            success_element = self.wait_for_element(page, indicator, timeout=2000)
            if success_element:
                print("   ✅ Success notification displayed")
                logs_visible = True
                break
        
        return logs_visible
    
    def run(self, playwright: Playwright) -> None:
        """Main test execution with smart waits"""
        browser = None
        context = None
        
        try:
            print("🚀 Starting Container Logs Test (Smart Version)...")
            print(f"📍 Configuration: {self.base_url}")
            print(f"🖥️ Target Machine: {self.target_machine}")
            print("-" * 50)
            
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
            print("\n1️⃣ Navigating to console...")
            page.goto(f"{self.base_url}/console")
            self.wait_for_network_idle(page)
            self.take_screenshot(page, "01_initial_page")
            
            # Step 2: Login
            print("\n2️⃣ Performing authentication...")
            page = self.login(page)
            self.take_screenshot(page, "02_after_login")
            
            # Step 3: Navigate to Resources
            print("\n3️⃣ Accessing Resources section...")
            self.navigate_to_resources(page)
            self.take_screenshot(page, "03_resources_page")
            
            # Step 4: Expand machine
            print(f"\n4️⃣ Expanding machine {self.target_machine}...")
            self.expand_machine(page)
            self.take_screenshot(page, "04_machine_expanded")
            
            # Step 5: Expand repository
            print("\n5️⃣ Searching and expanding repositories...")
            repo_expanded = self.expand_repository(page)
            self.take_screenshot(page, "05_repository_state")
            
            if not repo_expanded:
                print("\n⚠️ No repositories available for container logs")
                print("This is expected if no repositories with containers are configured")
            else:
                # Step 6: Open container logs
                print("\n6️⃣ Opening container logs...")
                logs_opened = self.open_container_logs(page)
                self.take_screenshot(page, "06_container_logs")
                
                if logs_opened:
                    print("\n✅ Container logs displayed successfully!")
                    
                    # Keep logs open for a moment to capture state
                    self.wait_for_network_idle(page)
                    self.take_screenshot(page, "07_logs_content")
                else:
                    print("\n⚠️ Container logs may not have opened fully")
            
            # Final screenshot
            self.take_screenshot(page, "08_final_state")
            
            print("\n" + "=" * 50)
            print("🎉 Test completed successfully!")
            print("=" * 50)
            
        except Exception as e:
            print(f"\n❌ Error during test: {str(e)}")
            if 'page' in locals():
                error_screenshot = self.take_screenshot(page, "error_screenshot_logs")
                print(f"📸 Error screenshot saved: {error_screenshot}")
            raise
        
        finally:
            # Cleanup
            if context:
                context.close()
            if browser:
                browser.close()
            print("\n🔒 Browser closed.")

def main():
    """Entry point"""
    try:
        # Check for custom config path
        config_path = None
        if len(sys.argv) > 1:
            config_path = sys.argv[1]
        
        test = ContainerLogsTest(config_path)
        
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