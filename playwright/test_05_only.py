#!/usr/bin/env python3
"""Test only test_repository_down.py with proper login"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))

from test_utils import TestBase

# Import the specific test module
import importlib.util
spec = importlib.util.spec_from_file_location("test_repository_down", Path(__file__).parent / "smart" / "test_repository_down.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RepoDownTest = module.RepoDownTest


class TestRunner(TestBase):
    def __init__(self):
        config_path = Path(__file__).parent / "config.json"
        super().__init__(str(config_path))
    
    def run(self, playwright):
        browser = self.create_browser(playwright)
        context = self.create_browser_context(browser)
        page = self.create_page_with_cache_disabled(context)
        
        try:
            # Login first
            login_url = f"{self.config['baseUrl']}/console/login"
            page.goto(login_url, wait_until="networkidle")
            
            # Fill login form
            email_input = page.get_by_test_id("login-email-input")
            email_input.fill(self.config['login']['credentials']['email'])
            
            password_input = page.get_by_test_id("login-password-input")
            password_input.fill(self.config['login']['credentials']['password'])
            
            submit_button = page.get_by_test_id("login-submit-button")
            submit_button.click()
            
            # Wait for dashboard
            page.wait_for_url("**/console/dashboard", timeout=10000)
            page.wait_for_load_state("networkidle")
            print("✓ Login successful")
            
            # Now run the repo down test
            test = RepoDownTest()
            success = test.run_with_page(page)
            
            print(f"\nTest result: {'PASSED' if success else 'FAILED'}")
            
            return success
            
        finally:
            context.close()
            browser.close()


def main():
    runner = TestRunner()
    
    with sync_playwright() as playwright:
        success = runner.run(playwright)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()