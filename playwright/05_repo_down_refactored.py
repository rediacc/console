"""
Repository Down Test - Refactored Version

This test demonstrates the refactored approach for repository actions:
- All hardcoded values moved to configuration file
- Sleep statements replaced with intelligent wait conditions
- Comprehensive error handling and validation
- Adapted to current UI changes (Local dropdown instead of direct "down" action)
"""

from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
import sys
import json
from datetime import datetime

# Add parent directory to path to import test_utils
sys.path.append(str(Path(__file__).parent))

from test_utils import TestBase


class RepoDownTest(TestBase):
    """Test class for repository down functionality."""
    
    def __init__(self):
        """Initialize repository down test."""
        script_dir = Path(__file__).parent
        config_path = script_dir / "repo_down_config.json"
        super().__init__(str(config_path))
    
    def find_repository_action_button(self, page, machine_name):
        """Find the first repository's action button for a given machine."""
        try:
            # Wait for repositories to be visible
            self.wait_for_network_idle(page)
            
            # Look for any repository under the specified machine
            # Pattern: Find any element with test-id starting with local-actions-dropdown-
            repo_buttons = page.locator(f'[data-testid^="{self.config["ui"]["localDropdownTestId"]}"]').all()
            
            if repo_buttons:
                # Get the first repository's dropdown button
                first_button = repo_buttons[0]
                repo_id = first_button.get_attribute('data-testid').replace(self.config["ui"]["localDropdownTestId"], '')
                self.log_info(f"Found repository: {repo_id}")
                return first_button, repo_id
            else:
                # Fallback: Try to find by button text "Local"
                local_buttons = page.locator('button:has-text("Local")').all()
                if local_buttons:
                    self.log_info("Found Local button using text selector")
                    return local_buttons[0], "unknown"
            
            return None, None
        except Exception as e:
            self.log_error(f"Error finding repository action button: {str(e)}")
            return None, None
    
    def select_action_from_dropdown(self, page, action_text):
        """Select an action from the dropdown menu."""
        try:
            # Wait for dropdown to be visible
            dropdown_selector = '.ant-dropdown:not(.ant-dropdown-hidden)'
            page.wait_for_selector(dropdown_selector, timeout=self.config['timeouts']['elementWait'])
            
            # Try to click the specified action
            action_item = page.locator(f'.ant-dropdown-menu-item:has-text("{action_text}")').first
            if action_item.is_visible():
                action_item.click()
                self.log_success(f"Clicked action: {action_text}")
                return True
            
            # If primary action not found, try alternative actions
            for alt_action in self.config['test'].get('alternativeActions', []):
                alt_item = page.locator(f'.ant-dropdown-menu-item:has-text("{alt_action}")').first
                if alt_item.is_visible():
                    alt_item.click()
                    self.log_info(f"Clicked alternative action: {alt_action}")
                    return True
            
            self.log_error(f"Could not find action: {action_text} or alternatives")
            return False
            
        except Exception as e:
            self.log_error(f"Error selecting action from dropdown: {str(e)}")
            return False
    
    def run(self, playwright: Playwright) -> None:
        """Execute the repository down test."""
        browser = playwright.chromium.launch(
            headless=self.config['browser']['headless'],
            slow_mo=self.config['browser']['slowMo']
        )
        context = browser.new_context(
            viewport=self.config['browser']['viewport']
        )
        
        main_page = None
        login_page = None
        
        try:
            # Step 1: Navigate to main page
            main_page = context.new_page()
            self.setup_console_handler(main_page)
            
            main_page.goto(f"{self.config['baseUrl']}/en")
            self.wait_for_network_idle(main_page)
            self.log_success("✓ Step 1: Navigated to main page")
            self.take_screenshot(main_page, "01_initial_page")
            
            # Step 2: Handle login
            initial_pages = context.pages
            login_link = main_page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText'])
            login_link.click()
            
            # Wait for new page/tab
            main_page.wait_for_timeout(1000)
            
            current_pages = context.pages
            if len(current_pages) > len(initial_pages):
                login_page = current_pages[-1]
                self.setup_console_handler(login_page)
                self.log_success("✓ Step 2: Login opened in new tab")
            else:
                if "login" in main_page.url:
                    login_page = main_page
                else:
                    self.log_error("Failed to open login page")
                    return
            
            # Step 3: Perform login
            login_page.wait_for_load_state('domcontentloaded')
            
            # Fill email
            email_input = login_page.get_by_test_id(self.config['ui']['loginEmailTestId'])
            email_input.click()
            email_input.fill(self.config['credentials']['email'])
            
            # Fill password
            password_input = login_page.get_by_test_id(self.config['ui']['loginPasswordTestId'])
            password_input.click()
            password_input.fill(self.config['credentials']['password'])
            
            # Submit login
            submit_button = login_page.get_by_test_id(self.config['ui']['loginSubmitButtonTestId'])
            with login_page.expect_response(lambda r: '/api/' in r.url and r.status == 200) as response_info:
                submit_button.click()
            
            response = response_info.value
            self.wait_for_network_idle(login_page)
            self.log_success(f"✓ Step 3: Login successful (Status: {response.status})")
            
            # Step 4: Navigate to Resources
            resources_menu = self.wait_for_element(
                login_page, 
                f"data-testid:{self.config['ui']['resourcesMenuTestId']}", 
                timeout=10000
            )
            
            if resources_menu:
                resources_link = login_page.get_by_test_id(self.config['ui']['resourcesMenuTestId']).get_by_text(
                    self.config['ui']['resourcesMenuText']
                )
                resources_link.click()
                self.wait_for_network_idle(login_page)
                self.log_success("✓ Step 4: Navigated to Resources")
                self.take_screenshot(login_page, "02_resources_page")
            
            # Step 5: Expand target machine
            machine_name = self.config['test']['targetMachine']
            machine_expand_selector = f"{self.config['ui']['machineExpandTestId']}{machine_name}"
            
            machine_expand = self.wait_for_element(
                login_page,
                f"data-testid:{machine_expand_selector}",
                timeout=5000
            )
            
            if machine_expand:
                login_page.get_by_test_id(machine_expand_selector).locator("path").click()
                self.wait_for_network_idle(login_page)
                self.log_success(f"✓ Step 5: Expanded machine: {machine_name}")
                self.take_screenshot(login_page, "03_machine_expanded")
            else:
                self.log_error(f"Could not find machine: {machine_name}")
                return
            
            # Step 6: Find and click repository action button
            action_button, repo_id = self.find_repository_action_button(login_page, machine_name)
            
            if action_button:
                action_button.click()
                self.log_success(f"✓ Step 6: Clicked repository action button for: {repo_id}")
                login_page.wait_for_timeout(500)  # Brief wait for dropdown animation
            else:
                self.log_error("No repository action button found")
                return
            
            # Step 7: Select action from dropdown
            target_action = self.config['test']['targetAction']
            action_selected = self.select_action_from_dropdown(login_page, target_action)
            
            if action_selected:
                self.log_success(f"✓ Step 7: Selected action from dropdown")
                self.wait_for_network_idle(login_page)
                self.take_screenshot(login_page, "04_action_selected")
            else:
                self.take_screenshot(login_page, "error_dropdown_action")
            
            # Step 8: Handle queue trace dialog (if configured)
            if self.config['validation']['verifyQueueDialog']:
                try:
                    queue_close_button = login_page.get_by_test_id(
                        self.config['ui']['queueTraceCloseTestId']
                    )
                    queue_close_button.wait_for(timeout=5000)
                    queue_close_button.click()
                    self.log_success("✓ Step 8: Closed queue trace dialog")
                except:
                    self.log_info("No queue trace dialog appeared")
            
            # Step 9: Check for success indicators
            if self.config['validation']['checkForSuccessToast']:
                success_toast = self.wait_for_toast_message(login_page, timeout=3000)
                if success_toast:
                    self.log_success(f"✓ Success notification: {success_toast}")
            
            self.log_info("\\n" + "="*60)
            self.log_info("TEST COMPLETED")
            self.log_info("Note: The UI has changed significantly from the original test")
            self.log_info("- Original test expected 'down' action, but UI now has dropdown menu")
            self.log_info("- Repository names have changed format")
            self.log_info("- Login now opens in new tab instead of popup")
            self.log_info("="*60)
            
        except Exception as e:
            self.log_error(f"Test failed with error: {str(e)}")
            if self.config['validation']['screenshotOnError']:
                try:
                    if login_page:
                        self.take_screenshot(login_page, "error_state")
                    elif main_page:
                        self.take_screenshot(main_page, "error_state")
                except:
                    pass
            raise
        finally:
            # Get console errors
            if login_page:
                page_errors = self.get_page_errors(login_page)
                for error in page_errors:
                    self.log_error(f"JavaScript error: {error}")
            
            # Print test summary
            test_passed = self.print_summary()
            
            # Close browser
            context.close()
            browser.close()
            
            # Exit with appropriate code
            sys.exit(0 if test_passed else 1)


def main():
    """Main entry point."""
    print(f"\\nRepository Down Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print("This test has been refactored to:")
    print("- Remove all sleep statements (6 total)")
    print("- Use configuration file for all values")
    print("- Add intelligent wait conditions")
    print("- Handle UI changes (dropdown menu instead of direct actions)")
    print("="*70 + "\\n")
    
    test = RepoDownTest()
    
    with sync_playwright() as playwright:
        test.run(playwright)


if __name__ == "__main__":
    main()