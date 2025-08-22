#!/usr/bin/env python3
"""
Login Test - Refactored to use SmartTestBase
"""

import sys
from pathlib import Path
from playwright.sync_api import Page

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from smart_test_base import SmartTestBase


class LoginTest(SmartTestBase):
    """Test class for login functionality."""
    
    def __init__(self):
        """Initialize login test."""
        super().__init__("LoginTest")
    
    def perform_login(self, page: Page) -> bool:
        """Perform login with configured credentials."""
        try:
            credentials = self.config['login']['credentials']
            timeouts = self.config['login']['timeouts']
            
            # Navigate to login page
            login_url = f"{self.config['baseUrl']}/console/login"
            self.log_info(f"Navigating to: {login_url}")
            
            page.goto(login_url, wait_until="networkidle")
            self.wait_for_network_idle(page)
            
            # Fill email
            self.log_info(f"Logging in as: {credentials['email']}")
            email_input = page.get_by_test_id("login-email-input")
            email_input.wait_for(state="visible", timeout=timeouts.get('element', 5000))
            email_input.fill(credentials['email'])
            
            # Fill password
            password_input = page.get_by_test_id("login-password-input")
            password_input.fill(credentials['password'])
            
            self.logger.log_test_step("login_credentials_filled", 
                                     "Login credentials entered")
            
            # Submit form
            submit_button = page.get_by_test_id("login-submit-button")
            
            # Capture login response
            with page.expect_response(lambda r: '/api/StoredProcedure/CreateAuthenticationRequest' in r.url) as response_info:
                submit_button.click()
            
            # Extract token from response
            response = response_info.value
            if response.status == 200:
                try:
                    login_data = response.json()
                    if hasattr(self, 'token_manager'):
                        self.token_manager.update_from_response(login_data)
                except Exception as e:
                    self.log_warning(f"Could not extract token: {e}")
            
            # Wait for dashboard
            dashboard_url = self.config['validation']['dashboardUrl']
            page.wait_for_url(dashboard_url, timeout=timeouts.get('navigation', 10000))
            self.wait_for_network_idle(page)
            
            self.log_success("Login successful! Dashboard loaded.")
            self.logger.info("Login completed successfully",
                           dashboard_loaded=True,
                           category="authentication")
            return True
            
        except Exception as e:
            self.log_error(f"Login failed: {str(e)}")
            self.logger.error("Login failed", error=e, category="authentication")
            return False
    
    def validate_dashboard(self, page: Page) -> bool:
        """Validate that dashboard loaded correctly."""
        try:
            # Check for dashboard elements
            dashboard_selectors = [
                "main-nav-dashboard",
                "main-nav-resources",
                "main-nav-monitoring"
            ]
            
            for selector in dashboard_selectors:
                try:
                    element = page.get_by_test_id(selector)
                    if element.is_visible():
                        self.log_info(f"Dashboard element found: {selector}")
                except:
                    self.log_warning(f"Dashboard element not found: {selector}")
            
            # Check welcome message if configured
            if 'welcomeMessage' in self.config.get('validation', {}):
                welcome_msg = self.config['validation']['welcomeMessage']
                if self.check_for_message(page, welcome_msg, timeout=3000)[0]:
                    self.log_success("Welcome message displayed")
            
            return True
            
        except Exception as e:
            self.log_error(f"Dashboard validation failed: {str(e)}")
            return False
    
    def run_with_page(self, page: Page) -> bool:
        """Execute the login test with existing page/session."""
        try:
            # Perform login
            if not self.perform_login(page):
                self.take_screenshot(page, "login_failed")
                return False
            
            # Validate dashboard
            self.validate_dashboard(page)
            
            # Take success screenshot
            self.take_screenshot(page, "login_success")
            
            return True
            
        except Exception as e:
            self.log_error(f"Test failed with exception: {str(e)}")
            self.take_screenshot(page, "login_exception")
            return False


# Standalone execution removed - use test_suite_runner.py to run tests