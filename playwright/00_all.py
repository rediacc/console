#!/usr/bin/env python3
"""
All Tests Runner - Execute all tests in sequence with shared browser session
This script runs all numbered tests (01-07) in order, reusing the browser session after login.
"""

import sys
import os
import json
import importlib.util
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, Page, Browser, BrowserContext
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from test_utils import TestBase, ConfigBuilder


class AllTestsRunner(TestBase):
    """Run all tests in sequence with shared browser session."""
    
    def __init__(self):
        """Initialize test runner."""
        script_dir = Path(__file__).parent
        config_path = script_dir / "config.json"
        super().__init__(str(config_path))
        
        # Test modules to run in order
        self.test_modules = [
            ('01_register_smart.py', 'RegistrationTest', True),   # Uses shared session
            ('03_createrepo_smart.py', 'run_with_page', True),    # Uses existing session
            ('04_Repo_edit_smart.py', 'RepoEditTest', True),      # Uses existing session
        ]
        
        self.test_results = []
    
    def load_test_module(self, module_file: str):
        """Dynamically load a test module."""
        module_path = Path(__file__).parent / module_file
        
        if not module_path.exists():
            self.log_error(f"Test module not found: {module_file}")
            return None
            
        # Load module dynamically
        spec = importlib.util.spec_from_file_location(module_file.replace('.py', ''), module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        return module
    
    def run_test_module(self, module_file: str, test_class_name: str, page: Page, use_run_with_page: bool) -> bool:
        """Run a single test module with the shared page."""
        try:
            self.log_info(f"\n{'='*60}")
            self.log_info(f"Running test: {module_file}")
            self.log_info(f"{'='*60}")
            
            # Load the module
            module = self.load_test_module(module_file)
            if not module:
                return False
            
            if test_class_name == 'run_with_page':
                # Call the run_with_page function directly from the module
                if hasattr(module, 'run_with_page'):
                    repo_name = module.run_with_page(page, self.config)
                    self.log_success(f"Test completed successfully. Created repo: {repo_name}")
                    return True
                else:
                    self.log_error(f"Function 'run_with_page' not found in {module_file}")
                    return False
            else:
                # Get the test class
                test_class = getattr(module, test_class_name, None)
                if not test_class:
                    self.log_error(f"Test class '{test_class_name}' not found in {module_file}")
                    return False
                
                # Create test instance
                test_instance = test_class()
                
                # Use run_with_page method if available and requested
                if use_run_with_page and hasattr(test_instance, 'run_with_page'):
                    success = test_instance.run_with_page(page)
                    # Print test summary if available
                    if hasattr(test_instance, 'print_summary'):
                        test_instance.print_summary()
                    return success
                else:
                    self.log_warning(f"Test {module_file} needs run_with_page method")
                    return False
            
        except Exception as e:
            self.log_error(f"Error running test {module_file}: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def perform_login(self, page: Page) -> bool:
        """Perform login using 02_login_smart.py logic."""
        try:
            # Navigate to login page
            login_url = f"{self.config['baseUrl']}/console/login"
            self.log_info(f"Navigating to: {login_url}")
            page.goto(login_url, wait_until="networkidle")
            
            # Fill login form
            email = self.config['login']['credentials']['email']
            password = self.config['login']['credentials']['password']
            
            self.log_info(f"Logging in as: {email}")
            
            # Fill email
            email_input = page.get_by_test_id("login-email-input")
            email_input.wait_for(state="visible", timeout=5000)
            email_input.fill(email)
            
            # Fill password
            password_input = page.get_by_test_id("login-password-input")
            password_input.fill(password)
            
            # Capture login response to get initial token
            with page.expect_response(lambda r: '/api/StoredProcedure/CreateAuthenticationRequest' in r.url) as response_info:
                submit_button = page.get_by_test_id("login-submit-button")
                submit_button.click()
            
            # Extract token from login response
            response = response_info.value
            if response.status == 200:
                try:
                    login_data = response.json()
                    self.token_manager.update_from_response(login_data)
                except Exception as e:
                    self.log_warning(f"Could not extract token from login response: {e}")
            
            # Wait for dashboard
            page.wait_for_url("**/console/dashboard", timeout=10000)
            page.wait_for_load_state("networkidle", timeout=10000)
            
            self.log_success("Login successful! Dashboard loaded.")
            return True
            
        except Exception as e:
            self.log_error(f"Login failed: {str(e)}")
            return False
    
    
    def run(self, playwright: Playwright) -> bool:
        """Execute all tests in sequence."""
        browser = None
        context = None
        page = None
        
        try:
            # Launch browser
            browser = self.create_browser(playwright)
            
            # Create context with cache disabled
            context = self.create_browser_context(browser)
            
            # Create single page for all tests with cache disabled
            page = self.create_page_with_cache_disabled(context)
            
            # Get page errors reference
            page_errors = self.get_page_errors(page)
            
            # Run tests in order
            all_passed = True
            
            # Test 1: Registration
            self.log_info("\n" + "="*60)
            self.log_info("Running Test 1: Registration")
            self.log_info("="*60)
            
            # Run registration test
            reg_module_file, reg_class_name, use_run_with_page = self.test_modules[0]
            reg_success = self.run_test_module(reg_module_file, reg_class_name, page, use_run_with_page)
            self.test_results.append(('01_register', reg_success, "Registration " + ("successful" if reg_success else "failed")))
            
            # If registration failed, try to login anyway
            if not reg_success:
                self.log_warning("Registration failed or user already exists, attempting login...")
            
            # Test 2: Login
            self.log_info("\n" + "="*60)
            self.log_info("Running Test 2: Login")
            self.log_info("="*60)
            
            login_success = self.perform_login(page)
            self.test_results.append(('02_login', login_success, "Login " + ("successful" if login_success else "failed")))
            
            if not login_success:
                self.log_error("Login failed - cannot continue with other tests")
                return False
            
            # Take screenshot after login
            self.take_screenshot(page, "02_login_success")
            
            # Run remaining tests using their run_with_page methods
            for module_file, test_class_name, use_run_with_page in self.test_modules[1:]:
                try:
                    # Check if page is still open
                    if page.is_closed():
                        self.log_error(f"Page was closed before running {module_file}. Recreating...")
                        page = self.create_page_with_cache_disabled(context)
                        # Re-login if page was recreated
                        if not self.perform_login(page):
                            self.log_error(f"Re-login failed for {module_file}")
                            self.test_results.append((module_file.replace('.py', ''), False, "Re-login failed"))
                            continue
                    
                    success = self.run_test_module(module_file, test_class_name, page, use_run_with_page)
                    self.test_results.append((module_file.replace('.py', ''), success, "Test " + ("passed" if success else "failed")))
                    if not success:
                        all_passed = False
                        # Continue with other tests even if one fails
                except Exception as e:
                    self.log_error(f"Unexpected error in {module_file}: {str(e)}")
                    self.test_results.append((module_file.replace('.py', ''), False, f"Failed with error: {str(e)}"))
                    all_passed = False
                    
                    # Try to recover by creating new page if current one is closed
                    if page.is_closed():
                        try:
                            page = self.create_page_with_cache_disabled(context)
                            self.perform_login(page)
                        except:
                            pass
            
            # Print final summary
            self.log_info("\n" + "="*60)
            self.log_info("TEST SUMMARY")
            self.log_info("="*60)
            
            for test_name, success, message in self.test_results:
                status = "✓ PASS" if success else "✗ FAIL"
                self.log_info(f"{status} - {test_name}: {message}")
            
            total_tests = len(self.test_results)
            passed_tests = sum(1 for _, success, _ in self.test_results if success)
            
            self.log_info(f"\nTotal: {passed_tests}/{total_tests} tests passed")
            
            return all_passed
            
        except Exception as e:
            self.log_error(f"Test runner failed with error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            if page:
                # Log any console errors
                if page_errors:
                    self.log_error(f"Console errors detected: {page_errors}")
            
            if context:
                context.close()
            if browser:
                browser.close()
            
            # Print test summary
            return self.print_summary()


def main():
    """Main entry point."""
    runner = AllTestsRunner()
    
    with sync_playwright() as playwright:
        success = runner.run(playwright)
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()