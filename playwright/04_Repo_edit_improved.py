"""
Improved Repository Edit Test

This test logs into the Rediacc console, navigates to the repository section,
and edits a repository name. All configuration is externalized and sleep
statements are replaced with intelligent wait conditions.
"""

from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
import sys
import os

# Add parent directory to path to import test_utils
sys.path.append(str(Path(__file__).parent))

from test_utils import TestBase


class RepoEditTest(TestBase):
    """Test class for repository editing functionality."""
    
    def __init__(self):
        """Initialize repository edit test."""
        # Get the directory where this script is located
        script_dir = Path(__file__).parent
        config_path = script_dir / "repo_edit_config.json"
        super().__init__(str(config_path))
    
    def run(self, playwright: Playwright) -> None:
        """Execute the repository edit test."""
        # Browser setup
        browser = playwright.chromium.launch(
            headless=self.config['browser']['headless'],
            slow_mo=self.config['browser']['slowMo']
        )
        context = browser.new_context(
            viewport=self.config['browser']['viewport']
        )
        
        try:
            # Navigate to main page
            main_page = context.new_page()
            main_page.goto(self.config['baseUrl'] + "/en")
            self.wait_for_network_idle(main_page)
            self.log_success("Navigated to main page")
            
            # Click login link and handle popup
            with main_page.expect_popup() as popup_info:
                main_page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText']).click()
            login_page = popup_info.value
            login_page.wait_for_load_state('domcontentloaded')
            self.log_success("Opened login popup")
            
            # Fill login credentials
            email_input = self.wait_for_element(login_page, f"data-testid:{self.config['ui']['loginEmailTestId']}")
            email_input.click()
            email_input.fill(self.config['credentials']['email'])
            self.log_info(f"Entered email: {self.config['credentials']['email']}")
            
            # Tab to password field and fill
            email_input.press("Tab")
            password_input = login_page.get_by_test_id(self.config['ui']['loginPasswordTestId'])
            password_input.fill(self.config['credentials']['password'])
            self.log_info("Entered password")
            
            # Submit login with API response wait
            submit_button = login_page.get_by_test_id(self.config['ui']['loginSubmitButtonTestId'])
            
            # Wait for login API response
            response = self.wait_for_api_response(
                login_page, 
                '/api/', 
                lambda: submit_button.click()
            )
            self.log_info(f"Login API response: {response.status}")
            
            # Wait for navigation after login
            login_page.wait_for_load_state('networkidle')
            
            # Check if we're logged in by looking for the resources menu
            resources_menu = self.wait_for_element(login_page, f"data-testid:{self.config['ui']['resourcesMenuTestId']}", timeout=10000)
            if resources_menu:
                self.log_success("Login successful - Dashboard loaded")
            
            # Navigate to Resources
            resources_menu.get_by_text(self.config['ui']['resourcesMenuText']).click()
            self.log_info("Clicked Resources menu")
            
            # Wait for resources page to load and click repositories tab
            repo_tab = self.wait_for_element(login_page, f"data-testid:{self.config['ui']['repositoriesTabTestId']}")
            repo_tab.click()
            self.log_success("Navigated to Repositories tab")
            
            # Wait for repository list to load
            self.wait_for_network_idle(login_page)
            
            # Find and click edit button for any repository
            # First, try to find any edit button in the repository list
            edit_button = None
            try:
                # Look for any edit button in the table
                edit_buttons = login_page.locator('[data-testid^="resources-repository-edit-"]').all()
                if edit_buttons:
                    # Click the first available edit button
                    edit_button = edit_buttons[0]
                    repo_name = edit_button.get_attribute('data-testid').replace('resources-repository-edit-', '')
                    self.log_info(f"Found repository to edit: {repo_name}")
                    edit_button.click()
                else:
                    self.log_error("No repositories found to edit")
                    return
            except Exception as e:
                self.log_error(f"Failed to find edit button: {str(e)}")
                # Try alternative selector
                try:
                    edit_button = login_page.locator('button:has-text("Edit")').first
                    edit_button.click()
                    self.log_info("Clicked edit button using alternative selector")
                except:
                    self.log_error("Could not find any edit button")
                    return
            
            # Wait for modal to appear
            modal_title = self.wait_for_element(login_page, 'text=Edit Repository Name', timeout=5000)
            if modal_title:
                self.log_success("Edit modal opened")
            
            # Fill repository name
            repo_name_input = self.wait_for_element(
                login_page, 
                f"data-testid:{self.config['ui']['repositoryNameInputTestId']}"
            )
            
            # Clear and fill new repository name
            self.fill_form_field(login_page, f'[data-testid="{self.config["ui"]["repositoryNameInputTestId"]}"]', 
                               self.config['repository']['targetRepoName'])
            self.log_info(f"Entered new repository name: {self.config['repository']['targetRepoName']}")
            
            # Check if there's a password field that needs to be filled
            try:
                # Try multiple selectors for password field
                password_selectors = [
                    '[data-testid*="credential"] input[type="password"]',
                    'input[placeholder*="Access Password"]',
                    'input[placeholder*="password"]',
                    '.ant-form-item-has-error input[type="password"]'
                ]
                
                password_field = None
                for selector in password_selectors:
                    try:
                        password_field = login_page.locator(selector).first
                        if password_field.is_visible():
                            break
                    except:
                        continue
                
                if password_field and password_field.is_visible():
                    password_field.click()
                    password_field.fill(self.config['repository']['accessPassword'])
                    self.log_info("Filled access password field")
            except:
                self.log_info("No password field found or not required")
            
            # Submit the form
            ok_button = login_page.get_by_test_id(self.config['ui']['modalOkButtonTestId'])
            
            # Check if button is enabled
            if self.wait_for_element_enabled(login_page, f'[data-testid="{self.config["ui"]["modalOkButtonTestId"]}"]'):
                # Click OK button and wait for API response
                response = self.wait_for_api_response(
                    login_page,
                    '/api/',
                    lambda: ok_button.click()
                )
                self.log_info(f"Update API response: {response.status}")
                
                # Check for success
                if response.status == 200:
                    self.log_success("Repository update request successful")
                    
                    # Wait for modal to close
                    try:
                        login_page.wait_for_selector('text=Edit Repository Name', state='hidden', timeout=5000)
                        self.log_success("Edit modal closed")
                    except:
                        self.log_info("Modal still visible, checking for errors")
                    
                    # Check for success toast/message
                    toast_message = self.wait_for_toast_message(login_page)
                    if toast_message:
                        self.log_success(f"Success message: {toast_message}")
                    
                    # Verify the repository name was updated in the list
                    try:
                        updated_repo = login_page.locator(f'text={self.config["repository"]["targetRepoName"]}').first
                        if updated_repo.is_visible():
                            self.log_success(f"Repository name updated to: {self.config['repository']['targetRepoName']}")
                    except:
                        self.log_info("Could not verify repository name in list")
                else:
                    self.log_error(f"Update failed with status: {response.status}")
            else:
                self.log_error("Save button is disabled - form validation may have failed")
                
                # Check for validation errors
                validation_errors = login_page.locator('.ant-form-item-explain-error').all()
                for error in validation_errors:
                    error_text = error.text_content()
                    self.log_error(f"Validation error: {error_text}")
            
            # Take final screenshot
            self.take_screenshot(login_page, "repo_edit_final")
            
        except Exception as e:
            self.log_error(f"Test failed with error: {str(e)}")
            # Take error screenshot
            try:
                self.take_screenshot(login_page, "repo_edit_error")
            except:
                pass
            raise
        finally:
            # Print summary
            self.print_summary()
            
            context.close()
            browser.close()


def main():
    """Main entry point."""
    test = RepoEditTest()
    
    with sync_playwright() as playwright:
        test.run(playwright)


if __name__ == "__main__":
    main()