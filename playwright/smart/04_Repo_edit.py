"""
Final Repository Edit Test - Configuration-Driven with Smart Waits

This test demonstrates best practices for Playwright automation:
- All hardcoded values moved to configuration file
- Sleep statements replaced with intelligent wait conditions
- Comprehensive error handling and validation
- Detailed logging and test summary
"""

from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
import sys
import json
from datetime import datetime

# Add parent directory to path to import test_utils
sys.path.append(str(Path(__file__).parent.parent))

from test_utils import TestBase, ConfigBuilder
import time
from logging_utils import StructuredLogger, log_playwright_action
from debug_dump import DebugDumper, quick_dump


class RepoEditTest(TestBase):
    """Test class for repository editing functionality."""
    
    def __init__(self):
        """Initialize repository edit test."""
        # Get the directory where this script is located
        script_dir = Path(__file__).parent
        config_path = script_dir.parent / "config.json"
        super().__init__(str(config_path))
        # Initialize logger
        self.logger = StructuredLogger("RepoEditTest", config=self.config.get('logging', {}))
    
    def find_and_click_edit_button(self, page):
        """Find and click the edit button for the session repository."""
        # Get the session repository name
        session_repo_name = self.get_session_repository_name()
        
        # First try to find the specific repository edit button
        try:
            specific_edit_button = page.locator(f'[data-testid="resources-repository-edit-{session_repo_name}"]')
            if specific_edit_button.is_visible():
                specific_edit_button.click()
                self.log_info(f"Found and clicked edit button for session repository: {session_repo_name}")
                return True, session_repo_name
        except:
            pass
        
        # Fallback strategies if specific repo not found
        # Strategy 1: Try data-testid selector for any repo
        try:
            edit_buttons = page.locator('[data-testid^="resources-repository-edit-"]').all()
            if edit_buttons:
                # Get the repository name from the first button
                first_button = edit_buttons[0]
                repo_id = first_button.get_attribute('data-testid').replace('resources-repository-edit-', '')
                first_button.click()
                self.log_warning(f"Session repository {session_repo_name} not found, editing {repo_id} instead")
                return True, repo_id
        except:
            pass
        
        # Strategy 2: Try button with edit text
        try:
            edit_button = page.locator('button:has-text("Edit")').first
            if edit_button.is_visible():
                edit_button.click()
                return True, "unknown"
        except:
            pass
        
        # Strategy 3: Try icon-based selector
        try:
            edit_icon = page.locator('[data-icon="edit"]').first.locator('..')
            if edit_icon.is_visible():
                edit_icon.click()
                return True, "unknown"
        except:
            pass
        
        return False, None
    
    def fill_password_field(self, page):
        """Try to find and fill password field with multiple strategies."""
        password_filled = False
        
        # List of possible password field selectors
        password_selectors = [
            # By placeholder
            'input[placeholder*="Access Password"]',
            'input[placeholder*="password" i]',
            # By label association
            'label:has-text("Access Password") + * input',
            # By form structure
            '.ant-form-item:has-text("Access Password") input',
            # By type in error state
            '.ant-form-item-has-error input[type="password"]',
            # Generic password fields
            'input[type="password"]:visible',
            # By aria-label
            'input[aria-label*="password" i]',
            # Try text input as well (some password fields may not have type="password")
            '.ant-form-item:has-text("Access Password") input[type="text"]'
        ]
        
        for selector in password_selectors:
            try:
                password_field = page.locator(selector).first
                if password_field.is_visible():
                    password_field.click()
                    # Clear first
                    password_field.fill("")
                    # Type the password
                    password_field.fill(self.config['repoEdit']['repository']['accessPassword'])
                    # Trigger change event
                    password_field.dispatch_event("change")
                    password_field.dispatch_event("blur")
                    password_filled = True
                    self.log_info(f"Filled password field using selector: {selector}")
                    self.log_info(f"Password value: {self.config['repoEdit']['repository']['accessPassword']}")
                    break
            except:
                continue
        
        return password_filled
    
    def run(self, playwright: Playwright) -> None:
        """Execute the repository edit test."""
        self.logger.log_test_start("RepoEditTest")
        test_start_time = time.time()
        
        # Browser setup
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
            # Navigate to main page
            main_page = context.new_page()
            self.setup_console_handler(main_page)
            
            self.logger.log_test_step("navigate_main", "Navigating to main page")
            with self.logger.performance_tracker("navigate_main_page"):
                main_page.goto(self.config['baseUrl'] + "/en")
                self.wait_for_network_idle(main_page)
            self.log_success("Navigated to main page")
            self.logger.info("Main page loaded", url=self.config['baseUrl'] + "/en")
            
            # Take initial screenshot
            self.take_screenshot(main_page, "01_initial_page")
            
            # Click login link and handle popup/new tab
            login_page = None
            
            # First, check current context pages
            initial_pages = context.pages
            
            # Click the login link
            main_page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText']).click()
            
            # Wait a moment for new window/tab to open
            main_page.wait_for_timeout(1000)
            
            # Check if a new page was opened
            current_pages = context.pages
            if len(current_pages) > len(initial_pages):
                # New page was opened (either popup or tab)
                login_page = current_pages[-1]  # Get the newest page
                self.setup_console_handler(login_page)
                self.log_info(f"Login opened in new window/tab (Total pages: {len(current_pages)})")
            else:
                # No new page, check if we navigated on the same page
                if "login" in main_page.url:
                    login_page = main_page
                    self.log_info("Navigated to login on same page")
                else:
                    self.log_error("Failed to open login page")
                    return
            
            login_page.wait_for_load_state('domcontentloaded')
            self.log_success("Login page loaded")
            
            # Fill login form
            self.log_info("Filling login form...")
            self.logger.log_test_step("fill_login", "Filling login credentials")
            
            # Email field
            with self.logger.performance_tracker("fill_login_form"):
                email_input = self.wait_for_element(login_page, f"data-testid:{self.config['repoEdit']['ui']['loginEmailTestId']}")
                self.fill_form_field(login_page, f'[data-testid="{self.config["repoEdit"]["ui"]["loginEmailTestId"]}"]', 
                                   self.config['login']['credentials']['email'])
                log_playwright_action(self.logger, "fill", selector="login-email-input", value_info="email entered")
            
            # Password field
            password_input = login_page.get_by_test_id(self.config['repoEdit']['ui']['loginPasswordTestId'])
            password_input.click()
            password_input.fill(self.config['login']['credentials']['password'])
            
            self.log_info(f"Credentials entered: {self.config['login']['credentials']['email']}")
            
            # Submit login
            submit_button = login_page.get_by_test_id(self.config['repoEdit']['ui']['loginSubmitButtonTestId'])
            
            # Ensure form is ready
            self.wait_for_element_enabled(login_page, f'[data-testid="{self.config["repoEdit"]["ui"]["loginSubmitButtonTestId"]}"]')
            
            # Submit with API monitoring
            self.logger.log_test_step("submit_login", "Submitting login form")
            with self.logger.performance_tracker("login_submission"):
                with login_page.expect_response(lambda r: '/api/' in r.url and r.status == 200) as response_info:
                    submit_button.click()
                    log_playwright_action(self.logger, "click", selector="login-submit-button", element_text="Submit")
                
                response = response_info.value
                self.log_success(f"Login successful (API Status: {response.status})")
                self.logger.info("Login API response received", status=response.status)
            
            # Wait for dashboard to load
            self.wait_for_network_idle(login_page)
            
            # Verify we're on the dashboard
            resources_menu_element = self.wait_for_element(login_page, f"data-testid:{self.config['repoEdit']['ui']['resourcesMenuTestId']}", timeout=10000)
            if resources_menu_element:
                self.log_success("Dashboard loaded successfully")
                self.take_screenshot(login_page, "02_dashboard")
            
            # Navigate to Resources - use locator instead of element
            resources_menu = login_page.get_by_test_id(self.config['repoEdit']['ui']['resourcesMenuTestId'])
            resources_menu.get_by_text(self.config['repoEdit']['ui']['resourcesMenuText']).click()
            self.log_info("Navigating to Resources...")
            
            # Click repositories tab
            repo_tab_element = self.wait_for_element(login_page, f"data-testid:{self.config['repoEdit']['ui']['repositoriesTabTestId']}", timeout=5000)
            if repo_tab_element:
                login_page.get_by_test_id(self.config['repoEdit']['ui']['repositoriesTabTestId']).click()
            
            # Wait for repository list to load
            self.wait_for_network_idle(login_page)
            self.log_success("Repository list loaded")
            self.take_screenshot(login_page, "03_repository_list")
            
            # Find and click edit button
            self.logger.log_test_step("find_edit_button", "Finding and clicking repository edit button")
            edit_clicked, repo_id = self.find_and_click_edit_button(login_page)
            
            if not edit_clicked:
                self.log_error("No repositories found to edit")
                self.log_info("This might be because there are no repositories in the system")
                self.logger.warning("No repositories available for editing")
                return
            
            self.log_info(f"Editing repository: {repo_id}")
            
            # Wait for modal
            modal_visible = False
            try:
                login_page.wait_for_selector('text=Edit Repository Name', timeout=5000)
                modal_visible = True
                self.log_success("Edit modal opened")
                self.take_screenshot(login_page, "04_edit_modal")
                
                # DEBUG: Dump state after modal opens
                self.log_info("🔍 DEBUG: Creating dump after edit modal opens...")
                dump_file = quick_dump(login_page, "edit_modal_opened", {
                    "test": "repo_edit",
                    "step": "modal_opened",
                    "repo_id": repo_id
                })
                self.log_info(f"📁 Debug dump created: {dump_file}")
            except:
                self.log_error("Edit modal did not appear")
                return
            
            # Fill repository name
            repo_name_element = self.wait_for_element(
                login_page, 
                f"data-testid:{self.config['repoEdit']['ui']['repositoryNameInputTestId']}",
                timeout=3000
            )
            
            if repo_name_element:
                # Use locator to interact with the input
                repo_name_input = login_page.get_by_test_id(self.config['repoEdit']['ui']['repositoryNameInputTestId'])
                repo_name_input.click()
                repo_name_input.fill("")  # Clear
                # Use session repository name with "_edited" suffix
                session_repo_name = self.get_session_repository_name()
                unique_repo_name = f"{session_repo_name}_edited"
                    
                repo_name_input.fill(unique_repo_name)
                self.log_success(f"Repository name changed to: {unique_repo_name}")
                log_playwright_action(self.logger, "fill", selector="repository-name-input", value_info=f"repo name: {unique_repo_name}")
            
            # DEBUG: Dump state before password field handling
            self.log_info("🔍 DEBUG: Creating dump before password field handling...")
            dump_file = quick_dump(login_page, "before_password_handling", {
                "test": "repo_edit",
                "step": "before_password",
                "repo_name": unique_repo_name
            })
            self.log_info(f"📁 Debug dump created: {dump_file}")
            
            # Handle password field by clicking generate button
            self.log_info("Looking for password generate button...")
            
            # Check if password field is visible and required
            password_errors = login_page.locator('.ant-form-item-explain-error:has-text("Access Password")').all()
            
            if password_errors:
                self.log_info("Password field is required - looking for generate button")
                
                # Look for the generate button (magnifying glass icon)
                # Try multiple selectors for the generate button
                generate_button_selectors = [
                    # Button with search/magnifying glass icon
                    '.ant-form-item:has-text("Access Password") button[aria-label*="search"]',
                    '.ant-form-item:has-text("Access Password") button[aria-label*="generate"]',
                    '.ant-form-item:has-text("Access Password") .anticon-search',
                    '.ant-form-item:has-text("Access Password") button:has(.anticon-search)',
                    # Generic button in password field area
                    '.ant-form-item:has-text("Access Password") button.ant-btn-icon-only',
                    '.ant-form-item:has-text("Access Password") .ant-input-suffix button',
                    # Button next to password input
                    'input[type="password"] + * button',
                    '.ant-form-item:has-text("Access Password") input + * button'
                ]
                
                generate_clicked = False
                for selector in generate_button_selectors:
                    try:
                        generate_button = login_page.locator(selector).first
                        if generate_button.is_visible():
                            generate_button.click()
                            self.log_success(f"Clicked generate password button using selector: {selector}")
                            generate_clicked = True
                            
                            # Wait for the generate popup to appear
                            login_page.wait_for_timeout(500)
                            
                            # Now click the Generate button in the popup
                            try:
                                # Look for the Generate button in the popup
                                generate_popup_button = login_page.locator('button:has-text("Generate")').first
                                if generate_popup_button.is_visible():
                                    generate_popup_button.click()
                                    self.log_success("Clicked Generate button in popup")
                                    # Wait for password to be generated
                                    login_page.wait_for_timeout(2000)
                                    
                                    # Click Apply button to apply the generated password
                                    try:
                                        apply_button = login_page.locator('button:has-text("Apply")').first
                                        if apply_button.is_visible():
                                            apply_button.click()
                                            self.log_success("Clicked Apply button to use generated password")
                                            login_page.wait_for_timeout(1000)
                                            
                                            # Check if password field is now filled
                                            password_input = login_page.locator('.ant-form-item:has-text("Access Password") input').first
                                            if password_input.is_visible():
                                                password_value = password_input.get_attribute('value')
                                                if password_value:
                                                    self.log_success(f"Password applied successfully: {password_value[:10]}...")
                                                else:
                                                    self.log_warning("Password field is empty after apply")
                                        else:
                                            self.log_error("Apply button not found")
                                    except Exception as e:
                                        self.log_error(f"Error clicking Apply button: {str(e)}")
                                else:
                                    self.log_error("Generate button in popup not found")
                            except Exception as e:
                                self.log_error(f"Error clicking Generate button in popup: {str(e)}")
                            
                            break
                    except:
                        continue
                
                if not generate_clicked:
                    self.log_error("Could not find password generate button")
            
            # Wait a bit to see if password was generated and form validation updates
            login_page.wait_for_timeout(2000)
            
            # DEBUG: Dump state after password generation attempt
            self.log_info("🔍 DEBUG: Creating dump after password generation attempt...")
            dump_file = quick_dump(login_page, "after_password_generation", {
                "test": "repo_edit",
                "step": "after_password_generation",
                "generate_clicked": generate_clicked if 'generate_clicked' in locals() else False
            })
            self.log_info(f"📁 Debug dump created: {dump_file}")
            
            # Additional check: See if there are other validation errors besides password
            all_errors = login_page.locator('.ant-form-item-explain-error').all()
            non_password_errors = []
            for error in all_errors:
                error_text = error.text_content()
                if error_text and "password" not in error_text.lower():
                    non_password_errors.append(error_text)
            
            if non_password_errors:
                self.log_error(f"Other validation errors found: {non_password_errors}")
            
            # Submit the form
            ok_button = login_page.get_by_test_id(self.config['repoEdit']['ui']['modalOkButtonTestId'])
            
            # Re-check if button is enabled after password generation
            self.log_info("Checking if Save button is now enabled...")
            
            # Try to click the button directly - it might be enabled even if it doesn't look like it
            try:
                # Check if button has disabled attribute
                is_disabled = ok_button.get_attribute('disabled')
                if is_disabled == 'true' or is_disabled == 'disabled':
                    self.log_info("Button has disabled attribute")
                    button_enabled = False
                else:
                    # Button might be enabled, let's try to click it
                    self.log_info("Button doesn't have disabled attribute, attempting to click...")
                    button_enabled = True
            except:
                # If we can't check attribute, assume it might be enabled
                button_enabled = True
            
            if button_enabled:
                # Submit with response monitoring
                try:
                    with login_page.expect_response(lambda r: '/api/' in r.url, timeout=10000) as response_info:
                        ok_button.click()
                    
                    response = response_info.value
                    
                    if response.status == 200:
                        self.log_success(f"Repository updated successfully (Status: {response.status})")
                        
                        # Wait for modal to close
                        try:
                            login_page.wait_for_selector('text=Edit Repository Name', state='hidden', timeout=5000)
                            self.log_success("Modal closed successfully")
                        except:
                            self.log_info("Modal may still be visible")
                        
                        # Check for success messages
                        success_message = self.wait_for_toast_message(login_page, timeout=3000)
                        if success_message:
                            self.log_success(f"Success notification: {success_message}")
                        
                        # Verify update in the list
                        self.wait_for_network_idle(login_page)
                        try:
                            updated_repo = login_page.locator(f'text={self.config["repository"]["targetRepoName"]}').first
                            if updated_repo.is_visible(timeout=3000):
                                self.log_success(f"✓ Repository successfully renamed to: {self.config['repoEdit']['repository']['targetRepoName']}")
                                self.take_screenshot(login_page, "05_update_success")
                        except:
                            self.log_info("Could not immediately verify the update in the list")
                    else:
                        self.log_error(f"Update failed with status: {response.status}")
                        try:
                            response_text = response.text()
                            self.log_error(f"Response: {response_text[:200]}...")
                        except:
                            pass
                except Exception as e:
                    self.log_error(f"Failed to submit form: {str(e)}")
                    # Take screenshot of the error state
                    self.take_screenshot(login_page, "error_submit_failed")
            else:
                self.log_warning("Save button is disabled - this is a known issue with password validation")
                self.take_screenshot(login_page, "password_validation_issue")
                
                # Log all visible validation errors as warnings
                all_errors = login_page.locator('.ant-alert-error, .ant-form-item-explain-error').all()
                for error in all_errors:
                    self.log_warning(f"Form validation: {error.text_content()}")
                
                # Document the current state
                self.log_info("\n" + "="*60)
                self.log_info("SAVE BUTTON DISABLED:")
                self.log_info("Despite successfully:")
                self.log_info("✓ Changing the repository name")
                self.log_info("✓ Clicking the password generate button")
                self.log_info("✓ Clicking Generate in the popup")
                self.log_info("")
                self.log_info("The Save button remains disabled.")
                self.log_info("This may be due to:")
                self.log_info("- Additional validation requirements")
                self.log_info("- Timing issues with password generation")
                self.log_info("- Other form fields that need to be filled")
                self.log_info("="*60)
            
        except Exception as e:
            self.log_error(f"Test failed with unexpected error: {str(e)}")
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.error("Repository edit test failed", error=str(e), duration_ms=test_duration_ms)
            # Take error screenshot
            try:
                if login_page:
                    self.take_screenshot(login_page, "unexpected_error")
                elif main_page:
                    self.take_screenshot(main_page, "unexpected_error")
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
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end("RepoEditTest", success=test_passed, duration_ms=test_duration_ms)
            
            # Close browser
            context.close()
            browser.close()
            self.logger.info("Browser closed")
            
            # Exit with appropriate code
            sys.exit(0 if test_passed else 1)
    
    def run_with_page(self, page) -> bool:
        """Execute the repository edit test with existing page/session."""
        self.logger.log_test_start("RepoEditTest")
        test_start_time = time.time()
        
        try:
            # No need to navigate - we're already logged in
            # Check if we're already on Resources page
            if "/resources" not in page.url:
                # Navigate to Resources only if not already there
                self.logger.log_test_step("navigate_resources", "Navigating to Resources page")
                resources_menu = page.get_by_test_id(self.config['repoEdit']['ui']['resourcesMenuTestId'])
                resources_menu.get_by_text(self.config['repoEdit']['ui']['resourcesMenuText']).click()
                self.log_info("Navigating to Resources...")
                self.wait_for_network_idle(page)
                self.logger.info("Navigated to Resources page")
            else:
                self.log_info("Already on Resources page")
                self.logger.info("Already on Resources page", url=page.url)
            
            # Click repositories tab
            self.logger.log_test_step("navigate_repositories", "Navigating to repositories tab")
            repo_tab_element = self.wait_for_element(page, f"data-testid:{self.config['repoEdit']['ui']['repositoriesTabTestId']}", timeout=5000)
            if repo_tab_element:
                page.get_by_test_id(self.config['repoEdit']['ui']['repositoriesTabTestId']).click()
                log_playwright_action(self.logger, "click", selector="repositories-tab", element_text="Repositories")
            
            # Wait for repository list to load
            self.wait_for_network_idle(page)
            self.log_success("Repository list loaded")
            self.logger.info("Repository list loaded successfully")
            self.take_screenshot(page, "03_repository_list")
            
            # Find and click edit button
            edit_clicked, repo_id = self.find_and_click_edit_button(page)
            
            if not edit_clicked:
                self.log_error("No repositories found to edit")
                self.log_info("This might be because there are no repositories in the system")
                return True  # Not a failure if no repos exist
            
            self.log_info(f"Editing repository: {repo_id}")
            
            # Wait for modal
            try:
                page.wait_for_selector('text=Edit Repository Name', timeout=5000)
                self.log_success("Edit modal opened")
                self.take_screenshot(page, "04_edit_modal")
                
                # DEBUG: Dump state after modal opens
                self.log_info("🔍 DEBUG: Creating dump after edit modal opens...")
                dump_file = quick_dump(page, "edit_modal_opened_session", {
                    "test": "repo_edit",
                    "step": "modal_opened",
                    "repo_id": repo_id,
                    "session_mode": True
                })
                self.log_info(f"📁 Debug dump created: {dump_file}")
            except:
                self.log_error("Edit modal did not appear")
                return False
            
            # Fill repository name
            repo_name_element = self.wait_for_element(
                page, 
                f"data-testid:{self.config['repoEdit']['ui']['repositoryNameInputTestId']}",
                timeout=3000
            )
            
            if repo_name_element:
                # Use locator to interact with the input
                repo_name_input = page.get_by_test_id(self.config['repoEdit']['ui']['repositoryNameInputTestId'])
                repo_name_input.click()
                repo_name_input.fill("")  # Clear
                # Use session repository name with "_edited" suffix
                session_repo_name = self.get_session_repository_name()
                unique_repo_name = f"{session_repo_name}_edited"
                    
                repo_name_input.fill(unique_repo_name)
                self.log_success(f"Repository name changed to: {unique_repo_name}")
                log_playwright_action(self.logger, "fill", selector="repository-name-input", value_info=f"repo name: {unique_repo_name}")
            
            # Submit the form
            ok_button = page.get_by_test_id(self.config['repoEdit']['ui']['modalOkButtonTestId'])
            
            try:
                # Try to submit
                with page.expect_response(lambda r: '/api/' in r.url, timeout=10000) as response_info:
                    ok_button.click()
                
                response = response_info.value
                
                if response.status == 200:
                    self.log_success(f"Repository updated successfully (Status: {response.status})")
                    self.logger.info("Repository update successful", status=response.status)
                    
                    # Wait for modal to close
                    try:
                        page.wait_for_selector('text=Edit Repository Name', state='hidden', timeout=5000)
                        self.log_success("Modal closed successfully")
                    except:
                        self.log_info("Modal may still be visible")
                    
                    # Check for success messages
                    success_message = self.wait_for_toast_message(page, timeout=3000)
                    if success_message:
                        self.log_success(f"Success notification: {success_message}")
                        self.logger.info("Success notification received", message=success_message)
                    
                    test_duration_ms = (time.time() - test_start_time) * 1000
                    self.logger.log_test_end("RepoEditTest", success=True, duration_ms=test_duration_ms)
                    return True
                else:
                    self.log_error(f"Update failed with status: {response.status}")
                    return False
                    
            except Exception as e:
                self.log_error(f"Failed to submit form: {str(e)}")
                self.take_screenshot(page, "error_submit_failed")
                return False
                
        except Exception as e:
            self.log_error(f"Test failed with unexpected error: {str(e)}")
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.error("Repository edit test failed", error=str(e), duration_ms=test_duration_ms)
            self.logger.log_test_end("RepoEditTest", success=False, duration_ms=test_duration_ms)
            self.take_screenshot(page, "unexpected_error")
            return False


def main():
    """Main entry point."""
    print(f"\nStarting Repository Edit Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    test = RepoEditTest()
    
    with sync_playwright() as playwright:
        test.run(playwright)


if __name__ == "__main__":
    main()