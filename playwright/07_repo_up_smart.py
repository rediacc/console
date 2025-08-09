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
            page.goto(self.config['baseUrl'] + "/en")
            page.wait_for_load_state('networkidle')
            self.log_success("Navigated to main page")
            self.take_screenshot(page, "01_main_page")
            
            # Click login link - it opens in a new page/tab
            with page.expect_popup() as popup_info:
                page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText']).click()
            login_page = popup_info.value
            
            # Wait for login page to load
            login_page.wait_for_load_state('networkidle')
            self.log_success("Login page opened")
            
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
            
            # Expand target machine
            machine_name = self.config['repoUp']['test']['targetMachine']
            self.log_info(f"Expanding machine: {machine_name}")
            
            machine_expand_selector = f"{self.config['repoUp']['ui']['machineExpandPrefix']}{machine_name}"
            machine_expand = login_page.get_by_test_id(machine_expand_selector)
            
            if machine_expand.is_visible():
                machine_expand.click()
                # Wait for repositories to be visible
                self.wait_for_element(login_page, 'h5:has-text("Repositories")')
                self.log_success(f"Machine {machine_name} expanded")
            
            # Click on machine's remote button
            self.log_info(f"Clicking remote button for machine: {machine_name}")
            
            machine_remote_selector = f"{self.config['repoUp']['ui']['machineRemotePrefix']}{machine_name}"
            machine_remote = login_page.get_by_test_id(machine_remote_selector)
            
            if machine_remote.is_visible():
                machine_remote.click()
                # Wait for machine to expand further
                page.wait_for_timeout(1000)
                self.log_success("Machine remote button clicked")
                
            # Now click on repository actions
            repo_name = self.config['repoUp']['test']['targetRepository']
            self.log_info(f"Clicking actions for repository: {repo_name}")
            
            repo_actions_selector = f"{self.config['repoUp']['ui']['repoActionsPrefix']}{repo_name}"
            repo_actions = login_page.get_by_test_id(repo_actions_selector)
            
            if repo_actions.is_visible():
                repo_actions.click()
                # Wait for dropdown menu
                self.wait_for_element(login_page, f'text={self.config["repoUp"]["ui"]["upActionText"]}')
                self.log_success("Repository actions menu opened")
                self.take_screenshot(login_page, "04_actions_menu")
                
            # Click "up" action from the dropdown
            self.log_info(f"Selecting '{self.config['repoUp']['test']['action']}' action...")
            up_action = login_page.get_by_text(self.config['repoUp']['ui']['upActionText'], exact=True)
            up_action.click()
            
            # Wait for success toast
            success_msg = self.config['repoUp']['validation']['successMessages']['queueCreated']
            toast_found = self.wait_for_toast(login_page, success_msg)
            if toast_found:
                self.log_success("Repository up operation queued successfully")
            
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
        page.on("console", lambda msg: test.console_handler(msg))
        
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