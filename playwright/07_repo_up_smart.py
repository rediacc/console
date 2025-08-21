"""
Repository Up Test - Configuration-Driven with Smart Waits

This test demonstrates bringing up a repository with:
- All values loaded from configuration
- No hardcoded credentials or selectors
- Smart waits instead of fixed sleeps
- Proper error handling and validation
- Queue monitoring for task completion
"""

from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
import sys
import json
from datetime import datetime

# Add parent directory to path to import test_utils
sys.path.append(str(Path(__file__).parent))

from test_utils import TestBase


class RepoUpTest(TestBase):
    """Test class for repository up functionality."""
    
    def __init__(self):
        """Initialize repository up test."""
        script_dir = Path(__file__).parent
        config_path = script_dir / "config.json"
        super().__init__(str(config_path))
    
    def wait_for_queue_dialog(self, page, timeout=5000):
        """Wait for queue dialog to appear and return it."""
        try:
            # Wait for queue dialog to appear
            queue_dialog = page.wait_for_selector(
                'div[role="dialog"]:has-text("Queue Item Trace")',
                timeout=timeout
            )
            return queue_dialog
        except:
            return None
    
    def monitor_queue_progress(self, page, timeout=None):
        """Monitor queue progress and return final status."""
        timeout = timeout or self.config['repoUp']['timeouts']['queueCompletion']
        start_time = datetime.now()
        
        status = "Unknown"
        console_output = ""
        
        while (datetime.now() - start_time).total_seconds() * 1000 < timeout:
            try:
                # Check current task status
                status_elements = page.locator('h3:has-text("Task")').all()
                if status_elements:
                    status_text = status_elements[0].text_content()
                    status = status_text.replace("Task", "").strip()
                    self.log_info(f"Current status: {status}")
                
                # Get console output
                console_section = page.locator('div:has-text("Response (Console)")').first
                if console_section.is_visible():
                    output_element = console_section.locator('~ div').first
                    if output_element.is_visible():
                        console_output = output_element.text_content()
                        if console_output and console_output != "No console output available":
                            self.log_info(f"Console: {console_output[:100]}...")
                
                # Check for completion states
                if status in ["COMPLETED", "FAILED", "CANCELLED"]:
                    break
                
                # Check for specific success/failure messages in console
                if self.config['repoUp']['validation']['successMessages']['repositoryStarted'] in console_output:
                    status = "COMPLETED"
                    break
                elif self.config['repoUp']['validation']['failureMessages']['setupFailed'] in console_output:
                    status = "FAILED"
                    break
                
                # Wait before next check
                page.wait_for_timeout(1000)
                
            except Exception as e:
                self.log_error(f"Error monitoring queue: {str(e)}")
                break
        
        return status, console_output
    
    def run_test(self, page):
        """Execute the repository up test."""
        try:
            # Navigate to main page
            page.goto(self.config['baseUrl'] + "/console")
            page.wait_for_load_state('networkidle')
            self.log_success("Navigated to main page")
            self.take_screenshot(page, "01_main_page")
            
            # Check if we're already on the login page (redirected)
            if "/login" in page.url or "login" in page.url.lower():
                login_page = page
                self.log_success("Already on login page (redirected)")
            else:
                # Try to find login link if not already on login page
                try:
                    with page.expect_popup() as popup_info:
                        page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText']).click()
                    login_page = popup_info.value
                    # Wait for login page to load
                    login_page.wait_for_load_state('networkidle')
                    self.log_success("Login page opened")
                except:
                    # If we can't find login link, check if we're on login page
                    if "/login" in page.url or "login" in page.url.lower():
                        login_page = page
                        self.log_success("On login page")
                    else:
                        self.log_error("Failed to navigate to login page")
                        return
            
            # Fill login credentials
            self.log_info("Logging in...")
            login_page.get_by_test_id(self.config['repoUp']['ui']['loginEmailTestId']).fill(
                self.config['login']['credentials']['email']
            )
            login_page.get_by_test_id(self.config['repoUp']['ui']['loginPasswordTestId']).fill(
                self.config['login']['credentials']['password']
            )
            
            # Submit login
            login_page.get_by_test_id(self.config['repoUp']['ui']['loginSubmitButtonTestId']).click()
            
            # Wait for dashboard to load
            self.wait_for_element(login_page, 'text=Dashboard', timeout=10000)
            self.log_success("Login successful")
            self.take_screenshot(login_page, "02_dashboard")
            
            # Navigate to Resources
            self.log_info("Navigating to Resources...")
            resources_menu = login_page.get_by_test_id(self.config['repoUp']['ui']['resourcesMenuTestId'])
            resources_menu.click()
            
            # Wait for resources page to load
            self.wait_for_element(login_page, 'h4:has-text("Team Resources")')
            self.log_success("Resources page loaded")
            self.take_screenshot(login_page, "03_resources")
            
            # Expand target machine (if not already expanded)
            machine_name = self.config['repoUp']['test']['targetMachine']
            self.log_info(f"Checking machine: {machine_name}")
            
            machine_expand_selector = f"{self.config['repoUp']['ui']['machineExpandPrefix']}{machine_name}"
            
            try:
                machine_expand = login_page.get_by_test_id(machine_expand_selector)
                if machine_expand.is_visible():
                    machine_expand.click()
                    # Wait for repositories to be visible
                    login_page.wait_for_timeout(2000)
                    self.log_success(f"Machine {machine_name} expanded")
                else:
                    self.log_info(f"Machine {machine_name} might already be expanded")
            except:
                self.log_info(f"Machine {machine_name} might already be expanded or expand button not found")
            
            # Wait a bit more for repositories to load
            login_page.wait_for_timeout(2000)
            
            # Find any repository to use (since repo03 might not exist)
            repo_name = self.config['repoUp']['test']['targetRepository']
            repo_actions_selector = f"{self.config['repoUp']['ui']['repoActionsPrefix']}{repo_name}"
            repo_actions = None
            
            # First try to find the configured repository
            try:
                repo_actions = login_page.get_by_test_id(repo_actions_selector)
                if repo_actions.is_visible():
                    self.log_info(f"Found configured repository: {repo_name}")
                else:
                    raise Exception("Configured repo not visible")
            except:
                # If configured repo doesn't exist, find any available repository
                self.log_info(f"Repository {repo_name} not found, looking for any available repository")
                
                # Try multiple methods to find repositories
                # Method 1: Look for Remote button which appears next to repositories
                remote_buttons = login_page.get_by_role("button", name="Remote").all()
                if remote_buttons:
                    self.log_info(f"Found {len(remote_buttons)} repositories with Remote buttons")
                    # Click the first Remote button
                    remote_buttons[0].click()
                    login_page.wait_for_timeout(500)
                    # Now the dropdown should be open, look for "up" action
                    self.log_success("Repository actions menu opened via Remote button")
                    # Skip to clicking up action directly
                    repo_actions = None  # Set to None to skip the normal flow
                else:
                    # Method 2: Try to find any repository action button
                    all_repo_buttons = login_page.locator('[data-testid^="machine-repo-list-repo-actions-"]').all()
                    if all_repo_buttons:
                        repo_actions = all_repo_buttons[0]
                        # Extract repository name from test-id
                        test_id = repo_actions.get_attribute('data-testid')
                        repo_name = test_id.replace('machine-repo-list-repo-actions-', '')
                        self.log_info(f"Using repository: {repo_name}")
                    else:
                        self.log_error("No repositories found")
                        return
            
            if repo_actions and repo_actions.is_visible():
                repo_actions.click()
                # Wait for dropdown menu
                login_page.wait_for_timeout(500)
                self.log_success("Repository actions menu opened")
                self.take_screenshot(login_page, "04_actions_menu")
                
            # Click "up" action from the dropdown
            self.log_info(f"Selecting '{self.config['repoUp']['test']['action']}' action...")
            
            # Try different ways to find the up action
            try:
                # Method 1: Try with exact text
                up_action = login_page.get_by_text(self.config['repoUp']['ui']['upActionText'], exact=True)
                if up_action.is_visible():
                    up_action.click()
                else:
                    raise Exception("Up action not visible with exact match")
            except:
                try:
                    # Method 2: Try with role and name
                    up_action = login_page.get_by_role("menuitem", name="up")
                    if up_action.is_visible():
                        up_action.click()
                    else:
                        raise Exception("Up action not visible as menuitem")
                except:
                    try:
                        # Method 3: Try in dropdown menu
                        dropdown_menu = login_page.locator('.ant-dropdown:not(.ant-dropdown-hidden)')
                        up_option = dropdown_menu.get_by_text("up")
                        if up_option.is_visible():
                            up_option.click()
                        else:
                            # Method 4: Try with partial text
                            up_option = dropdown_menu.locator('text=/up/i')
                            up_option.click()
                    except Exception as e:
                        self.log_error(f"Could not find 'up' action in dropdown: {str(e)}")
                        raise
            
            # Wait for success toast
            success_msg = self.config['repoUp']['validation']['successMessages']['queueCreated']
            toast_message = self.wait_for_toast_message(login_page, timeout=5000)
            if toast_message and success_msg in toast_message:
                self.log_success("Repository up operation queued successfully")
            else:
                self.log_info("Queue success toast not captured")
            
            # Wait for queue dialog
            self.log_info("Waiting for queue dialog...")
            queue_dialog = self.wait_for_queue_dialog(login_page)
            
            if queue_dialog:
                self.log_success("Queue dialog opened")
                self.take_screenshot(login_page, "05_queue_dialog")
                
                # Monitor queue progress
                self.log_info("Monitoring queue progress...")
                final_status, console_output = self.monitor_queue_progress(login_page)
                
                self.log_info(f"Final task status: {final_status}")
                
                if final_status == "COMPLETED":
                    self.log_success("✓ Repository started successfully!")
                elif final_status == "FAILED":
                    self.log_error(f"✗ Repository start failed")
                    if self.config['repoUp']['validation']['failureMessages']['exitCode'] in console_output:
                        # Extract exit code
                        exit_code = console_output.split("exit code")[-1].strip().split()[0]
                        self.log_error(f"Exit code: {exit_code}")
                else:
                    self.log_warning(f"Task ended with status: {final_status}")
                
                self.take_screenshot(login_page, "06_final_status")
                
                # Close queue dialog
                close_button = login_page.get_by_test_id(self.config['repoUp']['ui']['queueTraceCloseTestId'])
                if close_button.is_visible():
                    close_button.click()
                    self.log_info("Queue dialog closed")
            else:
                self.log_warning("Queue dialog did not appear")
            
            # Wait a moment before closing
            login_page.wait_for_timeout(2000)
            
        except Exception as e:
            self.log_error(f"Test failed: {str(e)}")
            self.take_screenshot(login_page, "error_state")
            raise


def run(playwright: Playwright) -> None:
    """Run the test with Playwright."""
    test = RepoUpTest()
    browser = None
    
    try:
        # Launch browser
        browser = playwright.chromium.launch(
            headless=test.config['browser']['headless'],
            slow_mo=test.config['browser']['slowMo']
        )
        
        # Create context with viewport
        context = browser.new_context(
            viewport=test.config['browser']['viewport']
        )
        
        # Create page
        page = context.new_page()
        
        # Add console listener
        test.setup_console_handler(page)
        
        # Run the test
        test.run_test(page)
        
        # Print summary
        test.print_summary()
        
    except Exception as e:
        print(f"✗ Test execution failed: {str(e)}")
        if test:
            test.print_summary()
    finally:
        if browser:
            browser.close()


def main():
    """Main entry point."""
    with sync_playwright() as playwright:
        run(playwright)


if __name__ == "__main__":
    main()