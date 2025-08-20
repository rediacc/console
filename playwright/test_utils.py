"""Common utilities for Playwright tests."""

import json
import re
import random
import string
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Route, Request, Response
from logging_utils import StructuredLogger, log_playwright_action, log_api_call, log_browser_console


class TestBase:
    """Base class for all Playwright tests."""
    
    # Class variable to store session repository name
    _session_repository_name: Optional[str] = None
    
    def __init__(self, config_path: str):
        """Initialize test with configuration."""
        self.config_path = config_path
        self.config = self.load_config(config_path)
        self.success_indicators: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.screenshots: List[str] = []
        self.console_errors: List[str] = []
        self.token_manager = TokenManager()
        
        # Initialize logger
        self.logger = StructuredLogger(
            name=self.__class__.__name__,
            config=self.config.get('logging', {})
        )
        
        # Initialize session repository name if not already set
        if TestBase._session_repository_name is None:
            TestBase._session_repository_name = self.generate_session_repository_name()
    
    @staticmethod
    def generate_session_repository_name() -> str:
        """Generate a random repository name for the session.
        Format: repo_XXXXXX where X is alphanumeric."""
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"repo_{suffix}"
    
    def get_session_repository_name(self) -> str:
        """Get the session repository name."""
        return TestBase._session_repository_name
    
    @classmethod
    def set_session_repository_name(cls, name: str):
        """Set the session repository name. Used by test runners to ensure consistency."""
        cls._session_repository_name = name
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def wait_for_element(self, page, selector: str, timeout: Optional[int] = None):
        """Wait for element to be visible and return it."""
        timeout = timeout or 5000
        start_time = time.time()
        
        try:
            if selector.startswith('data-testid:'):
                test_id = selector.replace('data-testid:', '')
                selector = f'[data-testid="{test_id}"]'
            
            self.logger.debug(f"Waiting for element: {selector}", selector=selector, timeout=timeout)
            element = page.wait_for_selector(selector, state='visible', timeout=timeout)
            
            duration_ms = (time.time() - start_time) * 1000
            log_playwright_action(self.logger, "wait_for_element", selector=selector, 
                                duration_ms=duration_ms, found=True)
            return element
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_playwright_action(self.logger, "wait_for_element", selector=selector, 
                                duration_ms=duration_ms, found=False, error=str(e))
            return None
    
    def wait_for_network_idle(self, page, timeout: Optional[int] = None):
        """Wait for network to be idle."""
        timeout = timeout or 30000
        try:
            page.wait_for_load_state('networkidle', timeout=timeout)
        except:
            # Don't fail if network doesn't idle
            pass
    
    def wait_for_api_response(self, page, url_pattern: str, action_func):
        """Execute action and wait for specific API response."""
        start_time = time.time()
        
        self.logger.debug(f"Waiting for API response: {url_pattern}", url_pattern=url_pattern)
        
        with page.expect_response(lambda response: url_pattern in response.url) as response_info:
            action_func()
        
        response = response_info.value
        duration_ms = (time.time() - start_time) * 1000
        
        # Log API call details
        log_api_call(self.logger, 
                    method=response.request.method,
                    url=response.url,
                    status_code=response.status,
                    duration_ms=duration_ms)
        
        return response
    
    def check_element_text(self, page, selector: str, expected_text: str, timeout: int = 5000) -> bool:
        """Check if element contains expected text."""
        try:
            page.wait_for_selector(f'{selector}:has-text("{expected_text}")', timeout=timeout)
            return True
        except:
            return False
    
    def check_for_message(self, page, message_pattern: str, timeout: int = 5000) -> Tuple[bool, Optional[str]]:
        """Check for message on page using pattern matching."""
        try:
            # Try exact match first
            element = page.wait_for_selector(f'text={message_pattern}', timeout=timeout//2)
            text = element.text_content()
            return True, text
        except:
            try:
                # Try regex match
                element = page.wait_for_selector(f'text=/{message_pattern}/', timeout=timeout//2)
                text = element.text_content()
                return True, text
            except:
                return False, None
    
    def take_screenshot(self, page, name: str) -> str:
        """Take a screenshot with timestamp."""
        try:
            # Check if page is still valid
            if page.is_closed():
                self.log_warning(f"Cannot take screenshot '{name}' - page is closed")
                return None
                
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{name}_{timestamp}.png"
            
            # Get the directory where the test script is located
            test_dir = Path(self.config_path).parent if hasattr(self, 'config_path') else Path.cwd()
            screenshots_dir = test_dir / "screenshots"
            
            # Create screenshots directory if it doesn't exist
            screenshots_dir.mkdir(exist_ok=True)
            filepath = str(screenshots_dir / filename)
            
            # Also save to log directory if available
            if hasattr(self.logger, 'log_dir'):
                log_screenshots_dir = self.logger.log_dir / "screenshots"
                log_screenshots_dir.mkdir(exist_ok=True)
                log_filepath = str(log_screenshots_dir / filename)
                page.screenshot(path=log_filepath)
            
            page.screenshot(path=filepath)
            self.screenshots.append(filepath)
            
            self.logger.info(f"Screenshot captured: {name}", 
                           screenshot_path=filepath,
                           page_url=page.url,
                           category="screenshot")
            
            return filepath
        except Exception as e:
            self.log_warning(f"Failed to take screenshot '{name}': {str(e)}")
            self.logger.error(f"Failed to capture screenshot: {name}", 
                            error=str(e),
                            category="screenshot")
            return None
    
    def log_success(self, message: str):
        """Log a success message."""
        self.success_indicators.append(f"✓ {message}")
        print(f"✓ {message}")
        self.logger.info(message, category="success", status="success")
    
    def log_error(self, message: str):
        """Log an error message."""
        self.errors.append(f"✗ {message}")
        print(f"✗ {message}")
        self.logger.error(message, category="error", status="error")
    
    def log_info(self, message: str):
        """Log an info message."""
        print(f"ℹ {message}")
        self.logger.info(message, category="info")
    
    def log_warning(self, message: str):
        """Log a warning message."""
        self.warnings.append(f"⚠ {message}")
        print(f"⚠ {message}")
        self.logger.warning(message, category="warning")
    
    def wait_for_element_enabled(self, page, selector: str, timeout: int = 5000) -> bool:
        """Wait for element to be enabled (not disabled)."""
        try:
            page.wait_for_function(
                f"""(selector) => {{
                    const element = document.querySelector(selector);
                    return element && !element.disabled;
                }}""",
                selector,
                timeout=timeout
            )
            return True
        except:
            return False
    
    def fill_form_field(self, page, selector: str, value: str, clear_first: bool = True):
        """Fill a form field with proper clearing and validation."""
        start_time = time.time()
        
        element = page.locator(selector)
        
        # Log click action
        element.click()
        log_playwright_action(self.logger, "click", selector=selector, 
                            purpose="focus_field")
        
        if clear_first:
            # Clear existing content
            element.fill("")
        
        # Fill the field (log sanitized value info)
        element.fill(value)
        duration_ms = (time.time() - start_time) * 1000
        
        # Log fill action without exposing sensitive data
        is_sensitive = any(field in selector.lower() for field in ['password', 'token', 'secret'])
        logged_value = "***SANITIZED***" if is_sensitive else f"{len(value)} characters"
        
        log_playwright_action(self.logger, "fill", selector=selector,
                            value_info=logged_value,
                            duration_ms=duration_ms)
        
        # Trigger change event
        element.dispatch_event("change")
    
    def print_summary(self):
        """Print test execution summary."""
        print("\n" + "="*50)
        print("TEST EXECUTION SUMMARY")
        print("="*50)
        
        summary_data = {
            "success_count": len(self.success_indicators),
            "warning_count": len(self.warnings),
            "error_count": len(self.errors),
            "screenshot_count": len(self.screenshots),
            "console_error_count": len(self.console_errors)
        }
        
        if self.success_indicators:
            print(f"\n✓ Success Indicators ({len(self.success_indicators)}):")
            for indicator in self.success_indicators:
                print(f"  {indicator}")
        
        if self.warnings:
            print(f"\n⚠ Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  {warning}")
        
        if self.errors:
            print(f"\n✗ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")
        
        if self.screenshots:
            print(f"\n📸 Screenshots ({len(self.screenshots)}):")
            for screenshot in self.screenshots:
                print(f"  {screenshot}")
        
        print("\n" + "="*50)
        
        # Log summary to structured logger
        test_passed = len(self.errors) == 0
        self.logger.info("Test execution summary",
                        category="test_summary",
                        passed=test_passed,
                        **summary_data)
        
        # Save summary to log directory
        if hasattr(self.logger, 'log_dir'):
            summary_file = self.logger.log_dir / "test_summary.json"
            with open(summary_file, 'w') as f:
                json.dump({
                    "test_name": self.__class__.__name__,
                    "passed": test_passed,
                    "timestamp": datetime.now().isoformat(),
                    "summary": summary_data,
                    "errors": self.errors,
                    "warnings": self.warnings,
                    "success_indicators": self.success_indicators,
                    "screenshots": self.screenshots
                }, f, indent=2)
        
        # Return test result
        return test_passed
    
    def wait_for_toast_message(self, page, timeout: int = 5000) -> Optional[str]:
        """Wait for and capture toast/notification messages."""
        try:
            # Common toast selectors
            toast_selectors = [
                '.ant-message',
                '.ant-notification',
                '[role="alert"]',
                '.toast',
                '.notification',
                '.alert'
            ]
            
            for selector in toast_selectors:
                try:
                    element = page.wait_for_selector(selector, timeout=timeout//len(toast_selectors))
                    if element:
                        return element.text_content()
                except:
                    continue
            
            return None
        except:
            return None
    
    def setup_console_handler(self, page):
        """Set up console message handler to collect errors."""
        def handle_console(msg):
            error_text = f"{msg.text}"
            
            # Log all console messages to structured logger
            log_browser_console(self.logger, 
                              message_type=msg.type,
                              message_text=error_text,
                              source=msg.location.get('url', '') if msg.location else '')
            
            if msg.type == 'error':
                self.console_errors.append(error_text)
                self.log_error(f"Console error: {error_text}")
        
        page.on('console', handle_console)
    
    def get_page_errors(self, page) -> List[str]:
        """Get console errors that have been collected.
        
        Note: setup_console_handler should be called on the page first.
        """
        return self.console_errors
    
    def create_browser(self, playwright: Playwright) -> Browser:
        """Create a browser instance with standard configuration."""
        self.logger.info("Creating browser instance",
                        headless=self.config['browser']['headless'],
                        slow_mo=self.config['browser']['slowMo'])
        
        browser = playwright.chromium.launch(
            headless=self.config['browser']['headless'],
            slow_mo=self.config['browser']['slowMo'],
            args=[
                '--start-maximized',  # Tam ekran başlatma argümanı
                '--disable-application-cache',  # Disable application cache
                '--disable-offline-load-stale-cache',  # Disable offline cache
                '--disable-gpu-shader-disk-cache',  # Disable GPU shader cache
                '--disable-dev-shm-usage',  # Disable /dev/shm usage
                '--aggressive-cache-discard',  # Aggressively discard cache
                '--disable-features=BackForwardCache',  # Disable back/forward cache
                '--disk-cache-size=1',  # Set disk cache to minimal size (1 byte)
                '--media-cache-size=1',  # Set media cache to minimal size
                '--memory-pressure-off'  # Disable memory pressure handling that might cache
            ]
        )
        
        self.logger.info("Browser instance created successfully")
        return browser
    
    def create_browser_context(self, browser: Browser) -> BrowserContext:
        """Create a browser context with cache disabled and standard configuration."""
        return browser.new_context(
            viewport=None,  # Viewport kısıtlamasını kaldır
            no_viewport=True,  # Browser pencere boyutunu kullan
            # Disable cache to always get fresh content
            bypass_csp=True,
            ignore_https_errors=True,
            # Force no caching via headers
            extra_http_headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0',
                'If-Modified-Since': '0',
                'If-None-Match': ''
            },
            # Disable service workers which can cache
            service_workers='block'
        )
    
    def create_page_with_cache_disabled(self, context: BrowserContext) -> Page:
        """Create a new page with cache disabled via CDP."""
        self.logger.info("Creating new page with cache disabled")
        
        page = context.new_page()
        
        # Disable cache using CDP (Chrome DevTools Protocol)
        cdp_session = context.new_cdp_session(page)
        
        # Disable network cache
        cdp_session.send("Network.setCacheDisabled", {"cacheDisabled": True})
        
        # Clear browser cache
        cdp_session.send("Network.clearBrowserCache")
        
        # Clear browser cookies (optional, uncomment if needed)
        # cdp_session.send("Network.clearBrowserCookies")
        
        # Set cache storage to bypass
        cdp_session.send("Network.setBypassServiceWorker", {"bypass": True})
        
        self.logger.debug("Cache disabled via CDP with multiple strategies")
        
        # Setup console error handler
        self.setup_console_handler(page)
        
        # Setup request/response interceptors for token management
        self.setup_api_interceptors(page)
        
        # Log page navigation events
        page.on('load', lambda: self.logger.info("Page loaded", url=page.url, category="navigation"))
        page.on('domcontentloaded', lambda: self.logger.debug("DOM content loaded", url=page.url, category="navigation"))
        
        self.logger.info("Page created and configured successfully")
        return page
    
    def setup_api_interceptors(self, page: Page):
        """Setup interceptors to handle API token rotation."""
        def handle_route(route: Route, request: Request):
            # Add current token to request headers if available
            headers = request.headers.copy()
            token = self.token_manager.get_token()
            if token and '/api/StoredProcedure' in request.url:
                headers['rediacc-requesttoken'] = token
            
            # Continue with modified headers
            route.continue_(headers=headers)
        
        # Intercept all requests to add token
        page.route('**/*', handle_route)
        
        # Monitor responses for token updates
        def handle_response(response: Response):
            try:
                if '/api/StoredProcedure' in response.url and response.status == 200:
                    # Try to parse response body
                    body = response.json()
                    self.token_manager.update_from_response(body)
            except Exception:
                pass
        
        page.on('response', handle_response)


class TokenManager:
    """Manages API token rotation for Rediacc API."""
    
    def __init__(self):
        self.current_token: Optional[str] = None
        self.is_updating = False
    
    def set_token(self, token: str):
        """Set the current token."""
        self.current_token = token
    
    def get_token(self) -> Optional[str]:
        """Get the current token."""
        return self.current_token
    
    def update_from_response(self, response_body: Dict[str, Any]):
        """Extract and update token from API response."""
        try:
            # Check for nextRequestToken in the response
            result_sets = response_body.get('resultSets', [])
            if result_sets and len(result_sets) > 0:
                data = result_sets[0].get('data', [])
                if data and len(data) > 0:
                    next_token = data[0].get('nextRequestToken')
                    if next_token:
                        self.set_token(next_token)
                        return True
        except Exception:
            pass
        return False


class ConfigBuilder:
    """Helper class to build test configurations dynamically."""
    
    @staticmethod
    def generate_unique_email(prefix: str = "test") -> str:
        """Generate a unique email address."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        return f"{prefix}_{timestamp}@rediacc.com"
    
    @staticmethod
    def generate_unique_name(prefix: str = "test") -> str:
        """Generate a unique name."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}"
    
    @staticmethod
    def merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two configuration dictionaries."""
        import copy
        result = copy.deepcopy(base_config)
        
        for key, value in override_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigBuilder.merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result