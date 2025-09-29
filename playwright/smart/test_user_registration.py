#!/usr/bin/env python3
"""
Registration Test for Rediacc Console
This test automates the user registration flow with proper wait conditions and error handling.
"""

import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from test_utils import TestBase, ConfigBuilder
import time


class RegistrationTest(TestBase):
    """Test class for user registration flow."""
    
    def __init__(self):
        """Initialize registration test."""
        # Get the directory where this script is located
        script_dir = Path(__file__).parent
        config_path = script_dir.parent / "config.json"
        super().__init__(str(config_path))
        
        # Generate unique email for this test run
        self.test_email = ConfigBuilder.generate_unique_email("register")
        self.config['registration']['email'] = self.test_email
    
    def wait_for_registration_form(self, page):
        """Wait for registration form to be fully loaded."""
        self.logger.log_test_step("wait_registration_form", "Waiting for registration form elements")
        
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
        self.logger.info("Registration form fully loaded", 
                        element_count=len(form_elements),
                        category="form_validation")
    
    def fill_registration_form(self, page):
        """Fill the registration form with test data."""
        ui_config = self.config['ui']
        reg_config = self.config['registration']
        
        self.logger.log_test_step("fill_registration_form", "Filling registration form fields")
        
        with self.logger.performance_tracker("fill_registration_form"):
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
        self.logger.info("Registration form filled",
                        company=reg_config['company'],
                        email=reg_config['email'],
                        category="form_data")
    
    def submit_registration(self, page):
        """Submit the registration form and handle response."""
        self.logger.log_test_step("submit_registration", "Submitting registration form")
        
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
            self.logger.warning("Registration failed: User already exists",
                              status_code=409,
                              category="registration_error")
            return False
        elif response.status >= 400:
            self.log_error(f"Registration failed with status: {response.status}")
            self.logger.error("Registration failed with error",
                            status_code=response.status,
                            category="registration_error")
            return False
        
        self.logger.info("Registration submitted successfully",
                        status_code=response.status,
                        category="registration_success")
        return True
    
    def handle_activation(self, page):
        """Handle the activation code step."""
        self.logger.log_test_step("handle_activation", "Processing activation code")
        
        with self.logger.performance_tracker("activation_process"):
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
                self.logger.info("Registration success message found",
                               success_msg=success_msg,
                               category="ui_validation")
            
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
            
            success = response.status < 400
            self.logger.info("Activation verification completed",
                           success=success,
                           status_code=response.status,
                           category="activation_result")
            
            return success
    
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
        self.logger.log_test_start("RegistrationTest", email=self.test_email)
        
        browser = self.create_browser(playwright)
        context = self.create_browser_context(browser)
        
        # Enable console message capture
        page = None
        test_start_time = time.time()
        
        try:
            # Step 1: Navigate to console login page directly
            page = self.create_page_with_cache_disabled(context)
            
            # Capture console errors
            page_errors = self.get_page_errors(page)
            
            with self.logger.performance_tracker("navigation_to_login"):
                page.goto(f"{self.config['baseUrl']}/console/login", wait_until='domcontentloaded')
                self.wait_for_network_idle(page)
            
            self.log_success("Navigated to console login page")
            
            # Step 2: Click Register to open registration modal
            self.logger.log_test_step("open_registration_modal", "Opening registration modal")
            
            register_link = page.get_by_text("Register")
            register_link.click()
            self.log_success("Opened registration modal")
            
            # Wait for registration form to appear in modal
            self.wait_for_element(page, "text:Create New Account", timeout=5000)
            self.logger.info("Registration modal displayed", category="ui_navigation")
            
            # Step 3: Fill registration form
            self.fill_registration_form(page)
            
            # Take screenshot before submission
            self.take_screenshot(page, "registration_form_filled")
            
            # Step 4: Submit registration
            if not self.submit_registration(page):
                # Check for error messages
                for error_key, error_pattern in self.config['registrationValidation']['errorMessages'].items():
                    found, error_text = self.check_for_message(page, error_pattern, timeout=2000)
                    if found:
                        self.log_error(f"Registration error: {error_text}")
                        self.logger.error("Registration error detected",
                                        error_type=error_key,
                                        error_text=error_text,
                                        category="registration_error")
                        if "already exists" in error_text:
                            self.log_info("User is already registered")
                        break
                
                self.take_screenshot(page, "registration_error")
                return False
            
            # Step 5: Handle activation
            if not self.handle_activation(page):
                self.log_error("Activation failed")
                self.take_screenshot(page, "activation_error")
                return False
            
            # Step 6: Check final state
            self.check_final_state(page)
            
            # Take success screenshot
            self.take_screenshot(page, "registration_success")
            
            # Log any console errors
            if page_errors:
                self.log_error(f"Console errors detected: {page_errors}")
            
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end("RegistrationTest", success=True, duration_ms=test_duration_ms)
            return True
            
        except Exception as e:
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.log_error(f"Test failed with exception: {str(e)}")
            self.logger.error("Registration test failed with exception",
                            error=e,
                            duration_ms=test_duration_ms,
                            category="test_failure")
            if page:
                self.take_screenshot(page, "test_exception")
            self.logger.log_test_end("RegistrationTest", success=False, duration_ms=test_duration_ms)
            raise
        
        finally:
            context.close()
            browser.close()
            
            # Print test summary
            return self.print_summary()
    
    def run_with_page(self, page) -> bool:
        """Execute the registration test with existing page/session."""
        self.logger.log_test_start("RegistrationTest (shared session)", email=self.test_email)
        test_start_time = time.time()
        
        try:
            # Navigate to console login page
            login_url = f"{self.config['baseUrl']}/console/login"
            
            with self.logger.performance_tracker("navigation_to_login"):
                page.goto(login_url, wait_until='domcontentloaded')
                self.wait_for_network_idle(page)
            
            self.log_success("Navigated to console login page")
            
            # Click Register to open registration modal
            self.logger.log_test_step("open_registration_modal", "Opening registration modal")
            
            register_link = page.get_by_text("Register")
            register_link.click()
            self.log_success("Opened registration modal")
            
            # Wait for registration form to appear in modal
            self.wait_for_element(page, "text:Create New Account", timeout=5000)
            self.logger.info("Registration modal displayed", category="ui_navigation")
            
            # Fill and submit form
            self.fill_registration_form(page)
            
            # Take screenshot before submission
            self.take_screenshot(page, "registration_form_filled")
            
            # Submit registration
            if not self.submit_registration(page):
                # Check for error messages
                for error_key, error_pattern in self.config['registrationValidation']['errorMessages'].items():
                    found, error_text = self.check_for_message(page, error_pattern, timeout=2000)
                    if found:
                        self.log_error(f"Registration error: {error_text}")
                        self.logger.error("Registration error detected",
                                        error_type=error_key,
                                        error_text=error_text,
                                        category="registration_error")
                        if "already exists" in error_text:
                            self.log_info("User is already registered")
                        break
                
                self.take_screenshot(page, "registration_error")
                return False
            
            # Handle activation
            if not self.handle_activation(page):
                self.log_error("Activation failed")
                self.take_screenshot(page, "activation_error")
                return False
            
            # Check final state
            self.check_final_state(page)
            
            # Take success screenshot
            self.take_screenshot(page, "registration_success")
            
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end("RegistrationTest (shared session)", success=True, duration_ms=test_duration_ms)
            return True
            
        except Exception as e:
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.log_error(f"Test failed with exception: {str(e)}")
            self.logger.error("Registration test failed with exception",
                            error=e,
                            duration_ms=test_duration_ms,
                            category="test_failure")
            self.take_screenshot(page, "test_exception")
            self.logger.log_test_end("RegistrationTest (shared session)", success=False, duration_ms=test_duration_ms)
            return False


# Standalone execution removed - use test_suite_runner.py to run tests