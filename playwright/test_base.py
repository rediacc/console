"""Base class for Playwright tests with common functionality"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from playwright.sync_api import Page, Browser, BrowserContext, Playwright, expect, sync_playwright


class PlaywrightTestBase:
    """Base class for Playwright tests with common utilities"""
    
    def __init__(self, config_path: str = 'config.json'):
        """Initialize test base with configuration"""
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.test_start_time = None
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_config_value(self, *keys: str, default: Any = None) -> Any:
        """Get nested configuration value safely"""
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def wait_for_element(
        self, 
        page: Page, 
        selector: str, 
        state: str = 'visible', 
        timeout: Optional[int] = None
    ) -> Optional[Any]:
        """Wait for element with configurable timeout and state"""
        if timeout is None:
            timeout = self.get_config_value('login', 'timeouts', 'element', default=5000)
        
        try:
            element = page.locator(selector)
            element.wait_for(state=state, timeout=timeout)
            return element
        except Exception as e:
            self.log(f"Element not found: {selector} - {str(e)}", level='warning')
            return None
    
    def wait_for_navigation(
        self, 
        page: Page, 
        url_pattern: Optional[str] = None, 
        timeout: Optional[int] = None
    ):
        """Wait for navigation with optional URL pattern check"""
        if timeout is None:
            timeout = self.get_config_value('login', 'timeouts', 'navigation', default=10000)
        
        try:
            if url_pattern:
                page.wait_for_url(url_pattern, timeout=timeout)
            else:
                page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception as e:
            self.log(f"Navigation timeout: {str(e)}", level='warning')
    
    def wait_for_network_idle(self, page: Page, timeout: Optional[int] = None):
        """Wait for network to be idle"""
        if timeout is None:
            timeout = self.get_config_value('login', 'timeouts', 'network', default=5000)
        
        try:
            page.wait_for_load_state('networkidle', timeout=timeout)
        except Exception as e:
            self.log(f"Network idle timeout: {str(e)}", level='warning')
    
    def take_screenshot(self, name: str, page: Optional[Page] = None):
        """Take a screenshot with timestamp"""
        if not self.get_config_value('screenshots', 'enabled', default=True):
            return
        
        page = page or self.page
        if not page:
            return
        
        screenshot_dir = Path(self.get_config_value('screenshots', 'path', default='./screenshots'))
        screenshot_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{name}_{timestamp}.png"
        filepath = screenshot_dir / filename
        
        try:
            page.screenshot(path=str(filepath))
            self.log(f"Screenshot saved: {filepath}")
        except Exception as e:
            self.log(f"Failed to take screenshot: {str(e)}", level='error')
    
    def log(self, message: str, level: str = 'info'):
        """Log message with timestamp and level"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        level_symbol = {
            'info': '📝',
            'success': '✅',
            'warning': '⚠️',
            'error': '❌',
            'debug': '🔍'
        }.get(level, '📝')
        
        print(f"[{timestamp}] {level_symbol} {message}")
    
    def login(self, page: Optional[Page] = None) -> Page:
        """Perform login with credentials from config"""
        page = page or self.page
        if not page:
            raise ValueError("No page available for login")
        
        self.log("Starting login process...")
        base_url = self.get_config_value('baseUrl')
        credentials = self.get_config_value('login', 'credentials')
        
        # Navigate to base URL
        page.goto(f"{base_url}/en")
        self.wait_for_navigation(page)
        
        # Click login link and wait for new page
        with page.expect_popup() as popup_info:
            login_link = page.get_by_role("banner").get_by_role("link", name="Login")
            login_link.click()
        
        login_page = popup_info.value
        
        # Wait for login form to be ready
        email_input = self.wait_for_element(login_page, '[data-testid="login-email-input"]')
        if not email_input:
            raise Exception("Login form not found")
        
        # Fill login credentials
        self.log(f"Logging in as {credentials['email']}...")
        email_input.click()
        email_input.fill(credentials['email'])
        
        password_input = login_page.get_by_test_id("login-password-input")
        password_input.click()
        password_input.fill(credentials['password'])
        
        # Submit login
        login_button = login_page.get_by_test_id("login-submit-button")
        login_button.click()
        
        # Wait for dashboard to load
        self.wait_for_navigation(login_page, "**/console/dashboard")
        
        # Verify login success
        dashboard_heading = self.wait_for_element(login_page, 'h2:has-text("Dashboard")')
        if dashboard_heading:
            self.log("Login successful!", level='success')
        else:
            raise Exception("Login failed - Dashboard not loaded")
        
        return login_page
    
    def setup_browser(self, playwright: Playwright) -> Browser:
        """Setup browser with configuration"""
        browser_config = self.get_config_value('browser', default={})
        
        browser = playwright.chromium.launch(
            headless=browser_config.get('headless', False),
            slow_mo=browser_config.get('slowMo', 0)
        )
        
        self.browser = browser
        return browser
    
    def setup_context(self) -> BrowserContext:
        """Setup browser context"""
        if not self.browser:
            raise ValueError("Browser not initialized")
        
        self.context = self.browser.new_context()
        return self.context
    
    def cleanup(self):
        """Clean up browser resources"""
        if self.context:
            self.context.close()
            self.context = None
        
        if self.browser:
            self.browser.close()
            self.browser = None
    
    def run_test(self, playwright: Playwright):
        """Override this method in subclasses to implement test logic"""
        raise NotImplementedError("Subclasses must implement run_test method")
    
    def execute(self):
        """Execute the test with proper setup and cleanup"""
        self.test_start_time = datetime.now()
        self.log(f"Starting test: {self.__class__.__name__}")
        
        with sync_playwright() as playwright:
            try:
                self.setup_browser(playwright)
                self.setup_context()
                self.run_test(playwright)
                
                test_duration = (datetime.now() - self.test_start_time).total_seconds()
                self.log(f"Test completed successfully in {test_duration:.2f} seconds", level='success')
                
            except Exception as e:
                self.log(f"Test failed: {str(e)}", level='error')
                self.take_screenshot("error")
                raise
                
            finally:
                self.cleanup()
    
    def check_element_text(self, page: Page, selector: str, expected_text: str) -> bool:
        """Check if element contains expected text"""
        element = self.wait_for_element(page, selector)
        if element:
            actual_text = element.text_content()
            if expected_text in actual_text:
                return True
            else:
                self.log(f"Text mismatch - Expected: '{expected_text}', Actual: '{actual_text}'", level='warning')
        return False
    
    def safe_click(self, page: Page, selector: str, timeout: Optional[int] = None) -> bool:
        """Safely click an element with error handling"""
        element = self.wait_for_element(page, selector, timeout=timeout)
        if element:
            try:
                element.click()
                return True
            except Exception as e:
                self.log(f"Failed to click element: {selector} - {str(e)}", level='error')
        return False