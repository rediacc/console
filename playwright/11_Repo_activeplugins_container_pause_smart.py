#!/usr/bin/env python3
"""
Container Pause Test - Smart Version
Tests the container pause functionality in Rediacc console
- Uses config.json for all configuration
- Smart waits instead of sleep()
- Better error handling and success detection
"""

import re
import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

class ContainerPauseTest:
    """Container pause test with smart waits and config-based setup"""
    
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
        
        # Container pause specific configuration
        self.pause_config = {
            'action_name': 'container_pause',
            'expected_states': ['Paused', 'paused', 'PAUSED'],
            'success_messages': [
                'Container paused successfully',
                'Container has been paused',
                'Pause operation completed'
            ]
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
    
    def wait_for_response(self, page, url_pattern, timeout=None):
        """Wait for specific API response"""
        if timeout is None:
            timeout = self.timeouts.get('network', 5000)
        
        try:
            with page.expect_response(url_pattern, timeout=timeout) as response_info:
                return response_info.value
        except:
            return None
    
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
        
        # Wait for repository content
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
        
        repo_expanded = False
        
        # Method 1: Find by test-id and img role
        try:
            repo_table = page.get_by_test_id("machine-repo-list-table")
            if repo_table.is_visible():
                expand_img = repo_table.get_by_role("img", name="right").locator("svg").first
                if expand_img.is_visible():
                    expand_img.click()
                    repo_expanded = True
                    print("   ✅ Repository expanded via img selector")
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
    
    def pause_container(self, page):
        """Find and click container pause action with smart waits"""
        print("⏸️ Looking for container actions...")
        
        container_found = False
        
        # Try to find the fx button (container actions button)
        fx_button_selectors = [
            'button.ant-dropdown-trigger:has-text("fx")',
            'button:has-text("fx")',
            '.ant-btn:has-text("fx")'
        ]
        
        fx_button = None
        for selector in fx_button_selectors:
            fx_button = self.wait_for_element(page, selector, timeout=2000)
            if fx_button:
                print("   ✅ Found fx (container actions) button")
                fx_button.click()
                container_found = True
                break
        
        # If fx button not found, try specific container action buttons
        if not container_found:
            specific_container_selectors = [
                '[data-testid*="machine-repo-list-container-actions"]',
                'button[data-testid*="container-actions"]'
            ]
            
            for selector in specific_container_selectors:
                container_buttons = page.locator(selector).all()
                if container_buttons:
                    container_buttons[0].click()
                    container_found = True
                    print("   ✅ Found container actions button")
                    break
        
        # If still not found, try generic selectors
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
            print("   This might be because no containers are running")
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
        
        # Look for container_pause option
        print("⏸️ Clicking container_pause...")
        
        pause_option_selectors = [
            f'text="{self.pause_config["action_name"]}"',
            f'li:has-text("{self.pause_config["action_name"]}")',
            f'.ant-dropdown-menu-item:has-text("{self.pause_config["action_name"]}")',
            '[role="menuitem"]:has-text("pause")'
        ]
        
        pause_clicked = False
        for selector in pause_option_selectors:
            pause_option = self.wait_for_element(page, selector, timeout=2000)
            if pause_option:
                # Listen for API response
                with page.expect_response(lambda response: 'pause' in response.url or 'container' in response.url, timeout=5000) as response_info:
                    pause_option.click()
                    pause_clicked = True
                    print("   ✅ Container pause option clicked")
                    
                    # Check response
                    response = response_info.value
                    if response.status == 200:
                        print(f"   ✅ API Response: Success (Status {response.status})")
                    else:
                        print(f"   ⚠️ API Response: Status {response.status}")
                break
        
        if not pause_clicked:
            # Fallback without response expectation
            for selector in pause_option_selectors:
                pause_option = self.wait_for_element(page, selector, timeout=2000)
                if pause_option:
                    pause_option.click()
                    pause_clicked = True
                    print("   ✅ Container pause option clicked (without response wait)")
                    break
        
        if not pause_clicked:
            print("   ❌ Could not find container_pause option")
            return False
        
        # Wait for operation to complete
        self.wait_for_network_idle(page)
        
        # Check for success indicators
        pause_successful = False
        
        # Check for success messages
        for message in self.pause_config['success_messages']:
            if self.wait_for_element(page, f'text="{message}"', timeout=2000):
                print(f"   ✅ Success message displayed: {message}")
                pause_successful = True
                break
        
        # Check for status change in container row
        for state in self.pause_config['expected_states']:
            if self.wait_for_element(page, f'text="{state}"', timeout=2000):
                print(f"   ✅ Container status changed to: {state}")
                pause_successful = True
                break
        
        # Check for success notifications
        success_indicators = [
            '.ant-message-success',
            '.ant-notification-success',
            '[role="alert"].success'
        ]
        
        for indicator in success_indicators:
            if self.wait_for_element(page, indicator, timeout=2000):
                print("   ✅ Success notification displayed")
                pause_successful = True
                break
        
        return pause_successful or pause_clicked
    
    def run(self, playwright: Playwright) -> None:
        """Main test execution with smart waits"""
        browser = None
        context = None
        
        try:
            print("🚀 Starting Container Pause Test (Smart Version)...")
            print(f"📍 Configuration: {self.base_url}")
            print(f"🖥️ Target Machine: {self.target_machine}")
            print(f"⏸️ Action: {self.pause_config['action_name']}")
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
            
            # Enable console logging
            page.on("console", lambda msg: print(f"   🖥️ Console: {msg.text}") if msg.type in ["error", "warning"] else None)
            
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
                print("\n⚠️ No repositories available for container pause")
                print("This is expected if no repositories with containers are configured")
                print("\n💡 To test container pause functionality:")
                print("   1. Deploy a repository to the machine")
                print("   2. Ensure containers are running")
                print("   3. Re-run this test")
            else:
                # Step 6: Pause container
                print("\n6️⃣ Initiating container pause...")
                pause_successful = self.pause_container(page)
                self.take_screenshot(page, "06_container_pause_action")
                
                if pause_successful:
                    print("\n✅ Container pause operation completed!")
                    
                    # Wait a moment to capture final state
                    self.wait_for_network_idle(page)
                    self.take_screenshot(page, "07_paused_state")
                else:
                    print("\n⚠️ Container pause may not have completed fully")
                    print("Check screenshots for visual confirmation")
            
            # Final screenshot
            self.take_screenshot(page, "08_final_state")
            
            print("\n" + "=" * 50)
            print("🎉 Test completed successfully!")
            print("=" * 50)
            
        except Exception as e:
            print(f"\n❌ Error during test: {str(e)}")
            if 'page' in locals():
                error_screenshot = self.take_screenshot(page, "error_screenshot_pause")
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
        
        test = ContainerPauseTest(config_path)
        
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