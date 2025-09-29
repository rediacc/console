#!/usr/bin/env python3
"""
All Tests Runner - Execute all tests in sequence with shared browser session
This script runs all numbered tests (01-07) in order, reusing the browser session after login.
"""

import sys
import os
import json
import importlib.util
import time
import argparse
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, Page, Browser, BrowserContext
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from test_utils import TestBase, ConfigBuilder
from logging_utils import StructuredLogger


class AllTestsRunner(TestBase):
    """Run all tests in sequence with shared browser session."""
    
    def __init__(self, scenario_name: str = "full_suite"):
        """Initialize test runner with specified scenario.
        
        Args:
            scenario_name: Name of the scenario to run (default: full_suite)
        """
        script_dir = Path(__file__).parent
        config_path = script_dir.parent / "config.json"
        super().__init__(str(config_path))
        
        # Initialize session logger for orchestration
        self.session_logger = StructuredLogger(
            name="AllTestsRunner",
            session_id=self.logger.session_id,  # Use same session ID
            config=self.config.get('logging', {})
        )
        
        # Generate and log the session repository name
        self.session_repo_name = self.get_session_repository_name()
        self.log_info(f"Session repository name: {self.session_repo_name}")
        
        # Load test scenarios from JSON
        self.scenarios = self.load_scenarios()
        self.current_scenario = self.get_scenario(scenario_name)
        
        if not self.current_scenario:
            raise ValueError(f"Scenario '{scenario_name}' not found. Available scenarios: {self.list_scenario_names()}")
        
        # Log session initialization
        self.session_logger.info("Test session initialized",
                                session_repo_name=self.session_repo_name,
                                scenario_name=scenario_name,
                                scenario_description=self.current_scenario['description'],
                                category="session_lifecycle")
        
        # Load test modules from selected scenario
        self.test_modules = self.load_test_modules_from_scenario(self.current_scenario)
        
        self.test_results = []
        
        # Log test plan
        self.session_logger.info("Test execution plan",
                                scenario=scenario_name,
                                test_count=len(self.test_modules),
                                test_names=[module[0] for module in self.test_modules],
                                category="test_plan")
    
    def load_scenarios(self) -> Dict[str, Any]:
        """Load test scenarios from JSON configuration file."""
        scenarios_path = Path(__file__).parent / "test_scenarios.json"
        
        if not scenarios_path.exists():
            self.log_warning(f"Scenarios file not found at {scenarios_path}, using default")
            # Return default scenarios if file doesn't exist
            return {
                "scenarios": [
                    {
                        "name": "full_suite",
                        "description": "Default full test suite",
                        "tests": [
                            {"module": "test_user_registration.py", "class_name": "RegistrationTest", "use_run_with_page": True},
                            {"module": "test_repository_creation.py", "class_name": "run_with_page", "use_run_with_page": True},
                            {"module": "test_repository_edit.py", "class_name": "RepoEditTest", "use_run_with_page": True},
                            {"module": "test_repository_down.py", "class_name": "RepoDownTest", "use_run_with_page": True},
                            {"module": "test_repository_push.py", "class_name": "RepoPushTest", "use_run_with_page": True}
                        ]
                    }
                ]
            }
        
        with open(scenarios_path, 'r') as f:
            return json.load(f)
    
    def get_scenario(self, scenario_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific scenario by name."""
        for scenario in self.scenarios.get('scenarios', []):
            if scenario['name'] == scenario_name:
                return scenario
        return None
    
    def list_scenario_names(self) -> List[str]:
        """Get list of all available scenario names."""
        return [s['name'] for s in self.scenarios.get('scenarios', [])]
    
    def load_test_modules_from_scenario(self, scenario: Dict[str, Any]) -> List[Tuple[str, str, bool]]:
        """Load test modules from a scenario configuration."""
        test_modules = []
        for test in scenario['tests']:
            test_modules.append((
                test['module'],
                test['class_name'],
                test.get('use_run_with_page', True)
            ))
        return test_modules
    
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
        start_time = time.time()
        
        try:
            self.log_info(f"\n{'='*60}")
            self.log_info(f"Running test: {module_file}")
            self.log_info(f"{'='*60}")
            
            # Log test start
            self.session_logger.log_test_start(module_file,
                                             test_class=test_class_name,
                                             page_url=page.url if not page.is_closed() else "closed")
            
            # Load the module
            module = self.load_test_module(module_file)
            if not module:
                self.session_logger.error(f"Failed to load module: {module_file}")
                return False
            
            if test_class_name == 'run_with_page':
                # Call the run_with_page function directly from the module
                if hasattr(module, 'run_with_page'):
                    repo_name = module.run_with_page(page, self.config)
                    if repo_name:
                        self.log_success(f"Test completed successfully. Repository: {repo_name}")
                    else:
                        self.log_success("Test completed successfully")
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
                    
                    duration_ms = (time.time() - start_time) * 1000
                    self.session_logger.log_test_end(module_file, success=success, duration_ms=duration_ms)
                    return success
                else:
                    self.log_warning(f"Test {module_file} needs run_with_page method")
                    self.session_logger.warning(f"Test missing run_with_page: {module_file}")
                    return False
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.log_error(f"Error running test {module_file}: {str(e)}")
            self.session_logger.error(f"Test failed with exception: {module_file}",
                                    error=e,
                                    duration_ms=duration_ms)
            import traceback
            traceback.print_exc()
            return False
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self.session_logger.log_test_end(module_file,
                                           success=False,
                                           duration_ms=duration_ms)
    
    def perform_login(self, page: Page) -> bool:
        """Perform login using test_user_login.py logic."""
        try:
            with self.session_logger.performance_tracker("login_operation"):
                # Navigate to login page
                login_url = f"{self.config['baseUrl']}/console/login"
                self.log_info(f"Navigating to: {login_url}")
                self.session_logger.info("Navigating to login page", url=login_url)
                
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
            
            self.session_logger.log_test_step("login_credentials_filled", 
                                            "Login credentials entered")
            
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
            self.session_logger.info("Login completed successfully",
                                   dashboard_loaded=True,
                                   category="authentication")
            return True
            
        except Exception as e:
            self.log_error(f"Login failed: {str(e)}")
            self.session_logger.error("Login failed", error=e, category="authentication")
            return False
    
    
    def run(self, playwright: Playwright) -> bool:
        """Execute all tests in sequence."""
        browser = None
        context = None
        page = None
        session_start_time = time.time()
        
        try:
            self.session_logger.info("Starting test session",
                                   test_count=len(self.test_modules),
                                   category="session_lifecycle")
            
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
            
            # Check if registration test is in the scenario
            has_registration = any(m[0] == 'test_user_registration.py' for m in self.test_modules)
            
            if has_registration:
                # Test 1: Registration
                self.log_info("\n" + "="*60)
                self.log_info("Running Test 1: Registration")
                self.log_info("="*60)
                
                self.session_logger.log_test_step("registration_phase", "Starting registration test")
                
                # Run registration test
                reg_module_file, reg_class_name, use_run_with_page = self.test_modules[0]
                reg_success = self.run_test_module(reg_module_file, reg_class_name, page, use_run_with_page)
                self.test_results.append(('test_user_registration', reg_success, "Registration " + ("successful" if reg_success else "failed")))
                
                self.session_logger.info("Registration test completed",
                                       success=reg_success,
                                       category="test_result")
                
                # If registration failed, try to login anyway
                if not reg_success:
                    self.log_warning("Registration failed or user already exists, attempting login...")
            else:
                self.log_info("Registration test not included in scenario, skipping...")
            
            # Test 2: Login
            self.log_info("\n" + "="*60)
            self.log_info("Running Test 2: Login")
            self.log_info("="*60)
            
            self.session_logger.log_test_step("login_phase", "Starting login test")
            
            login_success = self.perform_login(page)
            self.test_results.append(('test_user_login', login_success, "Login " + ("successful" if login_success else "failed")))
            
            self.session_logger.info("Login test completed",
                                   success=login_success,
                                   category="test_result")
            
            if not login_success:
                self.log_error("Login failed - cannot continue with other tests")
                return False
            
            # Take screenshot after login
            self.take_screenshot(page, "test_login_success")
            
            # Determine which tests to run (skip registration if it was already run)
            tests_to_run = self.test_modules[1:] if has_registration else self.test_modules
            
            # Run remaining tests using their run_with_page methods
            for module_file, test_class_name, use_run_with_page in tests_to_run:
                try:
                    # Check if page is still open
                    if page.is_closed():
                        self.log_error(f"Page was closed before running {module_file}. Recreating...")
                        self.session_logger.warning("Page closed, recreating",
                                                  test=module_file,
                                                  category="page_lifecycle")
                        
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
                    self.session_logger.error(f"Test failed unexpectedly: {module_file}",
                                            error=e,
                                            category="test_error")
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
            
            # Log session summary
            session_duration_ms = (time.time() - session_start_time) * 1000
            self.session_logger.info("Test session completed",
                                   total_tests=total_tests,
                                   passed_tests=passed_tests,
                                   failed_tests=total_tests - passed_tests,
                                   session_duration_ms=session_duration_ms,
                                   all_passed=all_passed,
                                   test_results=self.test_results,
                                   category="session_summary")
            
            # Save session summary to file
            if hasattr(self.session_logger, 'log_dir'):
                summary_file = self.session_logger.log_dir / "session_summary.json"
                with open(summary_file, 'w') as f:
                    json.dump({
                        "session_id": self.session_logger.session_id,
                        "total_tests": total_tests,
                        "passed_tests": passed_tests,
                        "failed_tests": total_tests - passed_tests,
                        "duration_ms": session_duration_ms,
                        "timestamp": datetime.now().isoformat(),
                        "test_results": [
                            {"name": name, "passed": success, "message": msg}
                            for name, success, msg in self.test_results
                        ]
                    }, f, indent=2)
            
            return all_passed
            
        except Exception as e:
            session_duration_ms = (time.time() - session_start_time) * 1000
            self.log_error(f"Test runner failed with error: {str(e)}")
            self.session_logger.critical("Test session failed catastrophically",
                                       error=e,
                                       session_duration_ms=session_duration_ms,
                                       category="session_error")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            if page:
                # Log any console errors
                if page_errors:
                    self.log_error(f"Console errors detected: {page_errors}")
                    self.session_logger.error("Browser console errors detected",
                                            error_count=len(page_errors),
                                            errors=page_errors[:10],  # Log first 10 errors
                                            category="browser_console")
            
            if context:
                context.close()
            if browser:
                browser.close()
            
            self.session_logger.info("Test session cleanup completed",
                                   category="session_lifecycle")
            
            # Print test summary
            return self.print_summary()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run Playwright smart test suite with scenario support")
    parser.add_argument(
        "--scenario",
        default="full_suite",
        help="Name of the scenario to run (default: full_suite)"
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List all available test scenarios"
    )
    
    args = parser.parse_args()
    
    # If listing scenarios, load and display them
    if args.list_scenarios:
        # Create a temporary runner just to load scenarios
        temp_runner = AllTestsRunner("full_suite")
        print("\nAvailable test scenarios:")
        print("="*60)
        for scenario in temp_runner.scenarios.get('scenarios', []):
            print(f"\nScenario: {scenario['name']}")
            print(f"Description: {scenario['description']}")
            print(f"Tests: {len(scenario['tests'])} test(s)")
            for test in scenario['tests']:
                print(f"  - {test['module']}: {test.get('description', 'No description')}")
        print("\n" + "="*60)
        print(f"\nUsage: python {Path(__file__).name} --scenario <scenario_name>\n")
        sys.exit(0)
    
    # Run the selected scenario
    try:
        runner = AllTestsRunner(args.scenario)
        print(f"\nRunning scenario: {args.scenario}")
        print(f"Description: {runner.current_scenario['description']}")
        print(f"Number of tests: {len(runner.test_modules)}\n")
        
        with sync_playwright() as playwright:
            success = runner.run(playwright)
            
            # Exit with appropriate code
            sys.exit(0 if success else 1)
            
    except ValueError as e:
        print(f"\nError: {e}")
        print("\nUse --list-scenarios to see available scenarios.")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()