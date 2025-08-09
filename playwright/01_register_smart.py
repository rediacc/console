#!/usr/bin/env python3
"""
Registration Test for Rediacc Console
This test automates the user registration flow with proper wait conditions and error handling.
"""

import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from test_utils import TestBase, ConfigBuilder


class RegistrationTest(TestBase):
    """Test class for user registration flow."""
    
    def __init__(self):
        """Initialize registration test."""
        # Get the directory where this script is located
        script_dir = Path(__file__).parent
        config_path = script_dir / "config.json"
        super().__init__(str(config_path))
        
        # Generate unique email for this test run
        self.test_email = ConfigBuilder.generate_unique_email("register")
        self.config['registration']['email'] = self.test_email
    
    def wait_for_registration_form(self, page):
        """Wait for registration form to be fully loaded."""
        # Wait for all form elements to be present
        form_elements = [
            self.config['ui']['companyInputTestId'],
            self.config['ui']['emailInputTestId'],
            self.config['ui']['passwordInputTestId'],
            self.config['ui']['passwordConfirmInputTestId'],
            self.config['ui']['submitButtonTestId']
        ]
        
        for element_id in form_elements:
            self.wait_for_element(page, f'data-testid:{element_id}')
        
        self.log_success("Registration form loaded")
    
    def fill_registration_form(self, page):
        """Fill the registration form with test data."""
        ui_config = self.config['ui']
        reg_config = self.config['registration']
        
        # Fill company name
        self.fill_form_field(
            page,
            f'[data-testid="{ui_config["companyInputTestId"]}"]',
            reg_config['company']
        )
        
        # Fill email
        self.fill_form_field(
            page,
            f'[data-testid="{ui_config["emailInputTestId"]}"]',
            reg_config['email']
        )
        
        # Fill password
        self.fill_form_field(
            page,
            f'[data-testid="{ui_config["passwordInputTestId"]}"]',
            reg_config['password']
        )
        
        # Fill password confirmation
        self.fill_form_field(
            page,
            f'[data-testid="{ui_config["passwordConfirmInputTestId"]}"]',
            reg_config['password']
        )
        
        self.log_success(f"Filled registration form with email: {reg_config['email']}")
    
    def submit_registration(self, page):
        """Submit the registration form and handle response."""
        submit_button = page.get_by_test_id(self.config['ui']['submitButtonTestId'])
        
        # Wait for button to be enabled
        self.wait_for_element_enabled(
            page,
            f'[data-testid="{self.config["ui"]["submitButtonTestId"]}"]'
        )
        
        # Submit form and wait for API response
        response = self.wait_for_api_response(
            page,
            '/api/',
            lambda: submit_button.click()
        )
        
        self.log_info(f"Registration API response: {response.status}")
        
        # Check response status
        if response.status == 409:
            self.log_error("User already exists")
            return False
        elif response.status >= 400:
            self.log_error(f"Registration failed with status: {response.status}")
            return False
        
        return True
    
    def handle_activation(self, page):
        """Handle the activation code step."""
        # Wait for activation code input
        activation_input = self.wait_for_element(
            page,
            f'data-testid:{self.config["ui"]["activationCodeInputTestId"]}',
            timeout=10000
        )
        
        # Check for success message
        success_msg = self.config['registrationValidation']['successMessages']['registrationSuccess']
        found, _ = self.check_for_message(page, success_msg)
        if found:
            self.log_success("Registration success message displayed")
        
        # Enter activation code
        self.fill_form_field(
            page,
            f'[data-testid="{self.config["ui"]["activationCodeInputTestId"]}"]',
            self.config['registration']['activationCode']
        )
        
        self.log_success("Entered activation code")
        
        # Submit verification
        verify_button = page.get_by_test_id(self.config['ui']['verifyButtonTestId'])
        
        response = self.wait_for_api_response(
            page,
            '/api/',
            lambda: verify_button.click()
        )
        
        self.log_info(f"Verification API response: {response.status}")
        
        return response.status < 400
    
    def check_final_state(self, page):
        """Check the final state after registration."""
        # Check for activation success message
        activation_msg = self.config['registrationValidation']['successMessages']['activationSuccess']
        found, _ = self.check_for_message(page, activation_msg)
        if found:
            self.log_success("Account activation confirmed")
        
        # Check for completion message
        completion_msg = self.config['registrationValidation']['successMessages']['registrationComplete']
        found, _ = self.check_for_message(page, completion_msg, timeout=3000)
        if found:
            self.log_success("Registration completed successfully")
        
        # Capture any toast messages
        toast_msg = self.wait_for_toast_message(page, timeout=2000)
        if toast_msg:
            self.log_info(f"Toast message: {toast_msg}")
    
    def run(self, playwright: Playwright) -> bool:
        """Execute the registration test."""
        browser = playwright.chromium.launch(
            headless=self.config['browser']['headless'],
            slow_mo=self.config['browser']['slowMo']
        )
        
        context = browser.new_context(
            viewport=self.config['browser']['viewport']
        )
        
        # Enable console message capture
        page = None
        
        try:
            # Step 1: Navigate to main page
            page = context.new_page()
            
            # Capture console errors
            page_errors = self.get_page_errors(page)
            
            page.goto(f"{self.config['baseUrl']}/en", wait_until='domcontentloaded')
            self.wait_for_network_idle(page)
            self.log_success("Navigated to main page")
            
            # Step 2: Open login popup
            with page.expect_popup() as popup_info:
                page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText']).click()
            
            login_page = popup_info.value
            login_page.wait_for_load_state('domcontentloaded')
            self.log_success("Opened login popup")
            
            # Step 3: Change language
            # First click on language dropdown to open it
            language_dropdown = login_page.locator(self.config['ui']['languageDropdownSelector']).first
            language_dropdown.wait_for(state='visible')
            language_dropdown.click()
            
            # Wait for dropdown options to appear
            login_page.wait_for_selector(self.config['ui']['languageDropdownOptionsSelector'], state='visible')
            
            # Now click on French option
            french_option = login_page.get_by_text(self.config['ui']['languageSelector'])
            french_option.wait_for(state='visible')
            french_option.click()
            
            # Wait for language change to take effect by checking for French text
            login_page.wait_for_selector('[data-testid="login-register-link"]', state='visible')
            self.log_success("Changed language to French")
            
            # Step 4: Navigate to registration
            register_link = login_page.get_by_test_id(self.config['ui']['registerLinkTestId'])
            register_link.click()
            
            # Wait for registration form
            self.wait_for_registration_form(login_page)
            
            # Step 5: Fill and submit form
            self.fill_registration_form(login_page)
            
            # Take screenshot before submission
            self.take_screenshot(login_page, "registration_form_filled")
            
            # Step 6: Submit registration
            if not self.submit_registration(login_page):
                # Check for error messages
                for error_key, error_pattern in self.config['registrationValidation']['errorMessages'].items():
                    found, error_text = self.check_for_message(login_page, error_pattern, timeout=2000)
                    if found:
                        self.log_error(f"Registration error: {error_text}")
                        if "already exists" in error_text:
                            self.log_info("User is already registered")
                        break
                
                self.take_screenshot(login_page, "registration_error")
                return False
            
            # Step 7: Handle activation
            if not self.handle_activation(login_page):
                self.log_error("Activation failed")
                self.take_screenshot(login_page, "activation_error")
                return False
            
            # Step 8: Check final state
            self.check_final_state(login_page)
            
            # Take success screenshot
            self.take_screenshot(login_page, "registration_success")
            
            # Log any console errors
            if page_errors:
                self.log_error(f"Console errors detected: {page_errors}")
            
            return True
            
        except Exception as e:
            self.log_error(f"Test failed with exception: {str(e)}")
            if page:
                self.take_screenshot(page, "test_exception")
            raise
        
        finally:
            context.close()
            browser.close()
            
            # Print test summary
            return self.print_summary()


def main():
    """Main entry point for the test."""
    test = RegistrationTest()
    
    with sync_playwright() as playwright:
        success = test.run(playwright)
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()