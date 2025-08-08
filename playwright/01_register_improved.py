import json
import re
from datetime import datetime
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


class RegistrationTest:
    def __init__(self, config_path="register_config.json"):
        """Initialize test with configuration."""
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Generate unique email with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.config['registration']['email'] = self.config['registration']['email'].replace('${timestamp}', timestamp)
        
        self.success_indicators = []
        self.errors = []
    
    def wait_for_element(self, page, test_id, timeout=None):
        """Wait for element to be visible and return it."""
        timeout = timeout or self.config['timeouts']['elementVisible']
        selector = f'[data-testid="{test_id}"]'
        element = page.wait_for_selector(selector, state='visible', timeout=timeout)
        return element
    
    def wait_for_network_idle(self, page):
        """Wait for network to be idle."""
        page.wait_for_load_state(self.config['timeouts']['networkIdle'])
    
    def check_for_success_message(self, page, message_key):
        """Check if success message appears on page."""
        expected_message = self.config['validation']['successMessages'][message_key]
        try:
            page.wait_for_selector(f'text={expected_message}', timeout=5000)
            self.success_indicators.append(f"✓ Found success message: {expected_message}")
            return True
        except:
            return False
    
    def check_for_error_message(self, page):
        """Check for any error messages."""
        for error_key, error_pattern in self.config['validation']['errorMessages'].items():
            try:
                # Use regex pattern matching for flexible error detection
                error_element = page.locator(f'text=/{error_pattern}/').first
                if error_element.is_visible():
                    error_text = error_element.text_content()
                    self.errors.append(f"✗ Error found: {error_text}")
                    return True, error_text
            except:
                pass
        return False, None
    
    def run(self, playwright: Playwright) -> None:
        """Execute the registration test."""
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
            page = context.new_page()
            page.goto(self.config['baseUrl'] + "/en", wait_until='domcontentloaded')
            self.wait_for_network_idle(page)
            print("✓ Navigated to main page")
            
            # Click login link and handle popup
            with page.expect_popup() as popup_info:
                page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText']).click()
            login_page = popup_info.value
            login_page.wait_for_load_state('domcontentloaded')
            print("✓ Opened login popup")
            
            # Change language to French
            login_page.get_by_text(self.config['ui']['languageSelector']).click()
            # Wait for language change to take effect
            login_page.wait_for_function("document.querySelector('[data-testid=\"login-register-link\"]') !== null")
            print("✓ Changed language to French")
            
            # Navigate to registration form
            self.wait_for_element(login_page, self.config['ui']['registerLinkTestId']).click()
            # Wait for registration form to be fully loaded
            self.wait_for_element(login_page, self.config['ui']['companyInputTestId'])
            print("✓ Opened registration form")
            
            # Fill registration form
            company_input = login_page.get_by_test_id(self.config['ui']['companyInputTestId'])
            company_input.click()
            company_input.fill(self.config['registration']['company'])
            
            email_input = login_page.get_by_test_id(self.config['ui']['emailInputTestId'])
            email_input.click()
            email_input.fill(self.config['registration']['email'])
            
            password_input = login_page.get_by_test_id(self.config['ui']['passwordInputTestId'])
            password_input.click()
            password_input.fill(self.config['registration']['password'])
            
            password_confirm_input = login_page.get_by_test_id(self.config['ui']['passwordConfirmInputTestId'])
            password_confirm_input.click()
            password_confirm_input.fill(self.config['registration']['password'])
            
            print(f"✓ Filled registration form with email: {self.config['registration']['email']}")
            
            # Submit registration
            submit_button = login_page.get_by_test_id(self.config['ui']['submitButtonTestId'])
            
            # Wait for form validation
            login_page.wait_for_function(
                """() => {
                    const button = document.querySelector('[data-testid="registration-submit-button"]');
                    return button && !button.disabled;
                }"""
            )
            
            # Click submit and wait for response
            with login_page.expect_response(lambda response: '/api/' in response.url) as response_info:
                submit_button.click()
            
            response = response_info.value
            print(f"✓ Submitted registration (Status: {response.status})")
            
            # Check for success or error
            error_found, error_text = self.check_for_error_message(login_page)
            if error_found:
                print(f"✗ Registration failed: {error_text}")
                if "already exists" in error_text:
                    print("  → User already registered")
                return
            
            # Wait for activation code input to appear
            activation_input = self.wait_for_element(login_page, self.config['ui']['activationCodeInputTestId'], timeout=10000)
            
            # Check for registration success message
            self.check_for_success_message(login_page, 'registrationSuccess')
            
            # Enter activation code
            activation_input.click()
            activation_input.fill(self.config['registration']['activationCode'])
            print("✓ Entered activation code")
            
            # Verify account
            verify_button = login_page.get_by_test_id(self.config['ui']['verifyButtonTestId'])
            
            with login_page.expect_response(lambda response: '/api/' in response.url) as response_info:
                verify_button.click()
            
            response = response_info.value
            print(f"✓ Submitted verification (Status: {response.status})")
            
            # Check for activation success
            self.check_for_success_message(login_page, 'activationSuccess')
            
            # Wait for final success state
            try:
                login_page.wait_for_selector('text=Inscription Terminée !', timeout=5000)
                print("✓ Registration completed successfully!")
            except:
                print("⚠ Could not confirm final registration completion")
            
            # Take screenshot of final state
            screenshot_path = f"registration_success_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            login_page.screenshot(path=screenshot_path)
            print(f"✓ Screenshot saved: {screenshot_path}")
            
        except Exception as e:
            print(f"✗ Test failed with error: {str(e)}")
            # Take error screenshot
            try:
                error_screenshot = f"registration_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                login_page.screenshot(path=error_screenshot)
                print(f"✓ Error screenshot saved: {error_screenshot}")
            except:
                pass
            raise
        finally:
            # Print summary
            print("\n=== Test Summary ===")
            if self.success_indicators:
                print("Success indicators found:")
                for indicator in self.success_indicators:
                    print(f"  {indicator}")
            if self.errors:
                print("Errors encountered:")
                for error in self.errors:
                    print(f"  {error}")
            
            context.close()
            browser.close()


def main():
    """Main entry point."""
    test = RegistrationTest()
    
    with sync_playwright() as playwright:
        test.run(playwright)


if __name__ == "__main__":
    main()