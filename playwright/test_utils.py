"""Common utilities for Playwright tests."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List


class TestBase:
    """Base class for all Playwright tests."""
    
    def __init__(self, config_path: str):
        """Initialize test with configuration."""
        self.config_path = config_path
        self.config = self.load_config(config_path)
        self.success_indicators: List[str] = []
        self.errors: List[str] = []
        self.screenshots: List[str] = []
        self.console_errors: List[str] = []
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def wait_for_element(self, page, selector: str, timeout: Optional[int] = None):
        """Wait for element to be visible and return it."""
        timeout = timeout or 5000
        try:
            if selector.startswith('data-testid:'):
                test_id = selector.replace('data-testid:', '')
                selector = f'[data-testid="{test_id}"]'
            
            element = page.wait_for_selector(selector, state='visible', timeout=timeout)
            return element
        except:
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
        with page.expect_response(lambda response: url_pattern in response.url) as response_info:
            action_func()
        
        response = response_info.value
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
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{name}_{timestamp}.png"
        
        # Get the directory where the test script is located
        test_dir = Path(self.config_path).parent if hasattr(self, 'config_path') else Path.cwd()
        screenshots_dir = test_dir / "screenshots"
        
        # Create screenshots directory if it doesn't exist
        screenshots_dir.mkdir(exist_ok=True)
        filepath = str(screenshots_dir / filename)
        
        page.screenshot(path=filepath)
        self.screenshots.append(filepath)
        return filepath
    
    def log_success(self, message: str):
        """Log a success message."""
        self.success_indicators.append(f"✓ {message}")
        print(f"✓ {message}")
    
    def log_error(self, message: str):
        """Log an error message."""
        self.errors.append(f"✗ {message}")
        print(f"✗ {message}")
    
    def log_info(self, message: str):
        """Log an info message."""
        print(f"ℹ {message}")
    
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
        element = page.locator(selector)
        element.click()
        
        if clear_first:
            # Clear existing content
            element.fill("")
        
        element.fill(value)
        
        # Trigger change event
        element.dispatch_event("change")
    
    def print_summary(self):
        """Print test execution summary."""
        print("\n" + "="*50)
        print("TEST EXECUTION SUMMARY")
        print("="*50)
        
        if self.success_indicators:
            print(f"\n✓ Success Indicators ({len(self.success_indicators)}):")
            for indicator in self.success_indicators:
                print(f"  {indicator}")
        
        if self.errors:
            print(f"\n✗ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")
        
        if self.screenshots:
            print(f"\n📸 Screenshots ({len(self.screenshots)}):")
            for screenshot in self.screenshots:
                print(f"  {screenshot}")
        
        print("\n" + "="*50)
        
        # Return test result
        return len(self.errors) == 0
    
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
            if msg.type == 'error':
                error_text = f"{msg.text}"
                self.console_errors.append(error_text)
                self.log_error(f"Console error: {error_text}")
        
        page.on('console', handle_console)
    
    def get_page_errors(self, page) -> List[str]:
        """Get console errors that have been collected.
        
        Note: setup_console_handler should be called on the page first.
        """
        return self.console_errors


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