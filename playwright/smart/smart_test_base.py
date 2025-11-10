#!/usr/bin/env python3
"""
Centralized base class for all smart tests.
Consolidates common functionality and provides consistent patterns.
"""

import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from playwright.sync_api import Page, Browser, BrowserContext, Playwright

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from test_utils import TestBase
from logging_utils import StructuredLogger


class SmartTestBase(TestBase):
    """Enhanced base class for smart tests with consolidated functionality."""
    
    def __init__(self, test_name: str, config_path: Optional[str] = None):
        """Initialize smart test with automatic config discovery."""
        if config_path is None:
            # Auto-discover config path
            script_dir = Path(__file__).parent
            config_path = script_dir.parent / "config.json"
        
        super().__init__(str(config_path))
        self.test_name = test_name
        
        # Initialize structured logger with test name
        self.logger = StructuredLogger(
            name=test_name,
            session_id=self.logger.session_id if hasattr(self, 'logger') else None,
            config=self.config.get('logging', {})
        )
    
    def navigate_to_resources(self, page: Page) -> bool:
        """Navigate to resources page using consistent approach."""
        try:
            self.logger.log_test_step("navigate_resources", "Navigating to Resources page")
            
            # Click Resources in navigation
            resources_nav = page.get_by_test_id("main-nav-machines")
            resources_nav.wait_for(state="visible", timeout=5000)
            resources_nav.click()
            
            # Wait for page load
            page.wait_for_url("**/console/resources", timeout=10000)
            self.wait_for_network_idle(page)
            
            self.log_success("Navigated to Resources page")
            return True
            
        except Exception as e:
            self.log_error(f"Failed to navigate to resources: {str(e)}")
            return False
    
    def find_repository_by_name(self, page: Page, repo_name: Optional[str] = None) -> Optional[str]:
        """Find repository by name or use session repository."""
        if repo_name is None:
            repo_name = self.get_session_repository_name()
        
        try:
            # Look for repository in the list
            repo_selector = f'tr:has-text("{repo_name}")'
            if page.locator(repo_selector).is_visible():
                self.log_info(f"Found repository: {repo_name}")
                return repo_name
                
        except Exception as e:
            self.log_warning(f"Repository {repo_name} not found: {str(e)}")
            
        return None
    
    def click_repository_action(self, page: Page, repo_name: str, action: str) -> bool:
        """Click an action button for a repository (edit, remote, etc)."""
        try:
            # Construct test-id for the action button
            button_testid = f"resources-repository-{action}-{repo_name}"
            button = page.get_by_test_id(button_testid)
            
            if button.is_visible():
                button.click()
                self.log_info(f"Clicked {action} for repository: {repo_name}")
                return True
            
            # Fallback: try finding in the repository row
            repo_row = page.locator(f'tr:has-text("{repo_name}")')
            if repo_row.is_visible():
                action_button = repo_row.locator(f'button:has-text("{action.capitalize()}")')
                if action_button.is_visible():
                    action_button.click()
                    self.log_info(f"Clicked {action} button using fallback selector")
                    return True
                    
        except Exception as e:
            self.log_error(f"Failed to click {action} for {repo_name}: {str(e)}")
            
        return False
    
    def wait_for_modal(self, page: Page, timeout: int = 5000) -> bool:
        """Wait for modal dialog to appear."""
        try:
            page.wait_for_selector('[role="dialog"]', state="visible", timeout=timeout)
            self.log_info("Modal dialog opened")
            return True
        except:
            self.log_error("Modal dialog did not appear")
            return False
    
    def fill_modal_field(self, page: Page, field_name: str, value: str) -> bool:
        """Fill a field in the resource modal."""
        try:
            # Try test-id first
            field_testid = f"resource-modal-field-{field_name}-input"
            field_input = page.get_by_test_id(field_testid)
            
            if field_input.is_visible():
                field_input.clear()
                field_input.fill(value)
                self.log_info(f"Filled {field_name} with: {value}")
                return True
                
            # Fallback: try by label
            label_selector = f'label:has-text("{field_name}")'
            label = page.locator(label_selector)
            if label.is_visible():
                field_input = label.locator('..').locator('input').first
                field_input.clear()
                field_input.fill(value)
                self.log_info(f"Filled {field_name} using label selector")
                return True
                
        except Exception as e:
            self.log_error(f"Failed to fill {field_name}: {str(e)}")
            
        return False
    
    def submit_modal(self, page: Page) -> bool:
        """Submit the modal form."""
        try:
            # Try multiple selectors for submit button
            submit_selectors = [
                '[data-testid="resource-modal-submit-button"]',
                'button:has-text("Submit")',
                'button:has-text("OK")',
                '.ant-modal-footer button.ant-btn-primary'
            ]
            
            for selector in submit_selectors:
                try:
                    submit_button = page.locator(selector).first
                    if submit_button.is_visible():
                        submit_button.click()
                        self.log_info("Submitted modal form")
                        return True
                except:
                    continue
                    
        except Exception as e:
            self.log_error(f"Failed to submit modal: {str(e)}")
            
        return False
    
    def verify_toast_message(self, page: Page, expected_text: str = None, timeout: int = 5000) -> Tuple[bool, Optional[str]]:
        """Verify toast notification message."""
        try:
            toast_selector = '.ant-message-notice'
            page.wait_for_selector(toast_selector, state="visible", timeout=timeout)
            
            toast = page.locator(toast_selector).first
            toast_text = toast.text_content()
            
            if expected_text:
                if expected_text in toast_text:
                    self.log_success(f"Toast message verified: {toast_text}")
                    return True, toast_text
                else:
                    self.log_warning(f"Toast text mismatch. Expected: {expected_text}, Got: {toast_text}")
                    return False, toast_text
            else:
                self.log_info(f"Toast message: {toast_text}")
                return True, toast_text
                
        except:
            self.log_warning("No toast message appeared")
            return False, None
    
    def run_with_page(self, page: Page) -> bool:
        """Abstract method to be implemented by specific tests."""
        raise NotImplementedError("Each test must implement run_with_page method")
    
    def run_test_with_session(self, page: Page) -> bool:
        """Wrapper for run_with_page with proper logging."""
        test_start_time = time.time()
        
        try:
            self.logger.log_test_start(self.test_name, page_url=page.url if not page.is_closed() else "closed")
            
            # Run the actual test
            success = self.run_with_page(page)
            
            duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end(self.test_name, success=success, duration_ms=duration_ms)
            
            return success
            
        except Exception as e:
            duration_ms = (time.time() - test_start_time) * 1000
            self.log_error(f"Test failed with exception: {str(e)}")
            self.logger.error(f"Test {self.test_name} failed with exception",
                            error=e,
                            duration_ms=duration_ms,
                            category="test_error")
            self.take_screenshot(page, f"{self.test_name}_exception")
            return False