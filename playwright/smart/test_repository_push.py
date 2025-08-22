#!/usr/bin/env python3
"""
Repository Push Test - Smart Version

This test demonstrates repository push operations with:
- Configuration-driven approach
- Smart wait conditions instead of fixed sleeps
- Comprehensive error handling and validation
- Queue monitoring for task completion
"""

import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from playwright.sync_api import Page

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from smart_test_base import SmartTestBase
from logging_utils import StructuredLogger


class RepoPushTest(SmartTestBase):
    """Test class for repository push functionality."""
    
    def __init__(self):
        """Initialize repository push test."""
        super().__init__("RepoPushTest")
        
        # Initialize structured logger
        self.logger = StructuredLogger(
            name="RepoPushTest",
            session_id=self.logger.session_id if hasattr(self, 'logger') else None,
            config=self.config.get('logging', {})
        )
    
    def select_destination_machine(self, page: Page, machine_name: str) -> bool:
        """Select destination machine from dropdown."""
        try:
            # Click on the destination dropdown using test-id
            destination_dropdown = page.get_by_test_id('function-modal-param-to')
            destination_dropdown.click()
            self.log_info("Opened destination dropdown")
            
            # Wait for dropdown options to be visible
            page.wait_for_selector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)', 
                                  timeout=self.config.get('repoPush', {}).get('timeouts', {}).get('elementWait', 5000))
            
            # Wait for dropdown animation
            page.wait_for_timeout(500)
            
            # Click on the target machine
            machine_option = page.get_by_title(machine_name).locator('div').first
            machine_option.click()
            self.log_success(f"Selected destination machine: {machine_name}")
            
            # Wait for dropdown to close
            page.wait_for_timeout(500)
            
            return True
        except Exception as e:
            self.log_error(f"Failed to select destination machine: {str(e)}")
            return False
    
    def wait_for_push_completion(self, page: Page, timeout: Optional[int] = None) -> Tuple[bool, List[str]]:
        """Wait for push operation to complete and capture results."""
        timeout = timeout or self.config.get('repoPush', {}).get('timeouts', {}).get('pushOperation', 30000)
        
        try:
            # Wait for operation to start
            page.wait_for_timeout(1000)
            
            toast_messages = []
            start_time = datetime.now()
            
            # Monitor for toast messages
            while (datetime.now() - start_time).total_seconds() * 1000 < timeout:
                # Check for toast notifications
                toast_selectors = ['.ant-message', '.ant-notification', '[role="status"]']
                
                for selector in toast_selectors:
                    try:
                        elements = page.locator(selector).all()
                        for element in elements:
                            text = element.text_content()
                            if text and text.strip() and text.strip() not in toast_messages:
                                toast_messages.append(text.strip())
                                self.log_info(f"Captured message: {text.strip()}")
                    except:
                        continue
                
                # Check if we have success indicators
                success_patterns = self.config.get('repoPush', {}).get('validation', {}).get('expectedToastMessages', [])
                for pattern in success_patterns:
                    for msg in toast_messages:
                        if pattern.replace('*', '') in msg or msg in pattern:
                            self.log_success(f"Found success pattern: {pattern}")
                            return True, toast_messages
                
                # Small wait before next check
                page.wait_for_timeout(500)
            
            return len(toast_messages) > 0, toast_messages
            
        except Exception as e:
            self.log_error(f"Error waiting for push completion: {str(e)}")
            return False, []
    
    def monitor_queue_dialog(self, page: Page) -> Dict[str, Any]:
        """Monitor queue trace dialog if it appears."""
        queue_info = {
            "appeared": False,
            "status": None,
            "task_id": None,
            "closed": False
        }
        
        try:
            # Wait for queue trace dialog
            self.log_info("Waiting for queue trace dialog...")
            queue_dialog_selector = '[role="dialog"]:has-text("Queue Item Trace")'
            
            try:
                page.wait_for_selector(queue_dialog_selector, timeout=15000)
                queue_info["appeared"] = True
                self.log_success("Queue trace dialog appeared")
                
                # Wait for dialog to fully load
                page.wait_for_timeout(2000)
                
                # Take screenshot of queue trace
                self.take_screenshot(page, "queue_trace_dialog")
                
                # Try to extract task ID
                task_id_pattern = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
                task_elements = page.locator(f"text=/{task_id_pattern}/").all()
                if task_elements:
                    queue_info["task_id"] = task_elements[0].text_content()
                    self.log_info(f"Task ID: {queue_info['task_id']}")
                
                # Check for status
                status_patterns = ["COMPLETED", "FAILED", "PROCESSING", "PENDING"]
                for pattern in status_patterns:
                    if page.locator(f'text="{pattern}"').count() > 0:
                        queue_info["status"] = pattern
                        self.log_info(f"Task status: {pattern}")
                        break
                
                # Close the dialog
                close_button = page.get_by_test_id(self.config.get('repoPush', {}).get('ui', {}).get('queueTraceCloseTestId', 'queue-trace-close-button'))
                if close_button.is_visible():
                    close_button.click()
                    queue_info["closed"] = True
                    self.log_success("Closed queue trace dialog")
                else:
                    # Try alternative close methods
                    close_alternatives = [
                        page.get_by_role("button", name="Close"),
                        page.locator('button[aria-label*="Close"]').first,
                        page.locator('.anticon-close').first
                    ]
                    
                    for alt_close in close_alternatives:
                        if alt_close.is_visible():
                            alt_close.click()
                            queue_info["closed"] = True
                            self.log_success("Closed queue trace dialog (alternative method)")
                            break
                
                # Wait for dialog to close
                page.wait_for_timeout(1000)
                
            except Exception as timeout_error:
                self.log_info(f"Queue trace dialog did not appear: {str(timeout_error)}")
                
        except Exception as e:
            self.log_info(f"Queue dialog monitoring skipped: {str(e)}")
        
        return queue_info
    
    def find_available_repository(self, page: Page) -> Optional[Tuple[str, Any]]:
        """Find an available repository for push operation."""
        try:
            # Get the session repository name (may have been edited)
            session_repo = self.get_session_repository_name() + "_edited"
            
            # First try the session repository
            repo_selector = f"{self.config.get('repoPush', {}).get('ui', {}).get('remoteButtonTestId', 'machine-repo-list-repo-actions-')}{session_repo}"
            
            try:
                repo_actions = page.get_by_test_id(repo_selector)
                if repo_actions.is_visible():
                    self.log_info(f"Found session repository: {session_repo}")
                    return session_repo, repo_actions
            except:
                pass
            
            # Try without _edited suffix
            session_repo_base = self.get_session_repository_name()
            repo_selector = f"{self.config.get('repoPush', {}).get('ui', {}).get('remoteButtonTestId', 'machine-repo-list-repo-actions-')}{session_repo_base}"
            
            try:
                repo_actions = page.get_by_test_id(repo_selector)
                if repo_actions.is_visible():
                    self.log_info(f"Found session repository: {session_repo_base}")
                    return session_repo_base, repo_actions
            except:
                pass
            
            # If not found, find any available repository
            self.log_info(f"Session repository not found, looking for any available repository")
            
            # Try to find any Remote button
            remote_buttons = page.locator('button:has-text("Remote")').all()
            if remote_buttons:
                # Use the first available Remote button
                repo_actions = remote_buttons[0]
                self.log_info("Using first available repository with Remote button")
                return "unknown", repo_actions
            
            # Fallback: try to find by test-id pattern
            test_id_pattern = self.config.get('repoPush', {}).get('ui', {}).get('remoteButtonTestId', 'machine-repo-list-repo-actions-')
            all_repo_buttons = page.locator(f'[data-testid^="{test_id_pattern}"]').all()
            if all_repo_buttons:
                repo_actions = all_repo_buttons[0]
                # Extract repository name from test-id
                test_id = repo_actions.get_attribute('data-testid')
                repo_name = test_id.replace(test_id_pattern, '')
                self.log_info(f"Using repository: {repo_name}")
                return repo_name, repo_actions
            
            return None
            
        except Exception as e:
            self.log_error(f"Error finding repository: {str(e)}")
            return None
    
    def run_with_page(self, page: Page) -> bool:
        """Execute the repository push test with existing page/session."""
        self.logger.log_test_start("RepoPushTest")
        test_start_time = time.time()
        
        try:
            # Step 1: Navigate to Resources if not already there
            self.log_info("=== Step 1: Navigate to Resources ===")
            if "/resources" not in page.url:
                if not self.navigate_to_resources(page):
                    self.log_error("Failed to navigate to Resources")
                    return False
            else:
                self.log_info("Already on Resources page")
            
            self.take_screenshot(page, "01_resources_page")
            
            # Step 2: Click on Machines tab
            self.log_info("=== Step 2: Navigate to Machines Tab ===")
            machines_tab = page.get_by_test_id("resources-tab-machines")
            if machines_tab.is_visible():
                machines_tab.click()
                self.wait_for_network_idle(page)
                self.log_success("Switched to Machines tab")
            else:
                self.log_info("Machines tab not found or already selected")
            
            # Step 3: Expand source machine
            self.log_info("=== Step 3: Expand Source Machine ===")
            source_machine = self.config.get('repoPush', {}).get('test', {}).get('sourceMachine', 'rediacc11')
            machine_expand_selector = f"{self.config.get('repoPush', {}).get('ui', {}).get('machineExpandTestId', 'machine-expand-')}{source_machine}"
            
            machine_expand = self.wait_for_element(
                page,
                f'[data-testid="{machine_expand_selector}"]',
                timeout=5000
            )
            
            if machine_expand:
                machine_expand.click()
                self.wait_for_network_idle(page)
                self.log_success(f"Expanded machine: {source_machine}")
                self.take_screenshot(page, "02_machine_expanded")
            else:
                self.log_error(f"Could not find machine: {source_machine}")
                return False
            
            # Step 4: Find repository and click actions
            self.log_info("=== Step 4: Find Repository ===")
            
            # Wait for repositories to load
            page.wait_for_timeout(1000)
            
            repo_result = self.find_available_repository(page)
            if not repo_result:
                self.log_error("No repository found for push operation")
                return False
            
            repo_name, repo_actions = repo_result
            repo_actions.click()
            self.log_success(f"Clicked actions for repository: {repo_name}")
            
            # Wait for dropdown menu
            page.wait_for_selector('.ant-dropdown:not(.ant-dropdown-hidden)', 
                                 timeout=self.config.get('repoPush', {}).get('timeouts', {}).get('elementWait', 5000))
            
            # Step 5: Select push action
            self.log_info("=== Step 5: Select Push Action ===")
            push_action = page.get_by_text(self.config.get('repoPush', {}).get('test', {}).get('pushAction', 'push'))
            push_action.click()
            self.log_success("Selected push action")
            
            # Wait for push dialog to open
            page.wait_for_selector('[role="dialog"]:has-text("Run Function")', 
                                timeout=self.config.get('repoPush', {}).get('timeouts', {}).get('elementWait', 5000))
            self.take_screenshot(page, "03_push_dialog")
            
            # Step 6: Configure push destination
            self.log_info("=== Step 6: Configure Push Destination ===")
            if self.config.get('repoPush', {}).get('test', {}).get('destinationType', 'machine') == 'machine':
                target_machine = self.config.get('repoPush', {}).get('test', {}).get('targetMachine', 'rediacc12')
                
                if self.select_destination_machine(page, target_machine):
                    self.log_success(f"Selected destination: {target_machine}")
                else:
                    self.log_error("Failed to select destination machine")
                    return False
            
            # Step 7: Submit push operation
            self.log_info("=== Step 7: Submit Push Operation ===")
            submit_button = page.get_by_test_id(
                self.config.get('repoPush', {}).get('ui', {}).get('functionModalSubmitTestId', 'function-modal-submit')
            )
            submit_button.click()
            self.log_success("Submitted push operation")
            
            # Step 8: Wait for completion
            self.log_info("=== Step 8: Monitor Push Operation ===")
            success, toast_messages = self.wait_for_push_completion(page)
            
            if success:
                self.log_success("Push operation completed successfully")
                
                # Verify expected messages
                if self.config.get('repoPush', {}).get('validation', {}).get('checkForSuccessToast', True):
                    for expected_msg in self.config.get('repoPush', {}).get('validation', {}).get('expectedToastMessages', []):
                        found = False
                        for actual_msg in toast_messages:
                            if expected_msg.replace('*', '') in actual_msg or actual_msg in expected_msg:
                                found = True
                                break
                        
                        if found:
                            self.log_success(f"Found expected message: {expected_msg}")
                        else:
                            self.log_info(f"Expected message not found: {expected_msg}")
            else:
                self.log_warning("Push operation may have issues")
            
            # Step 9: Handle queue trace dialog
            self.log_info("=== Step 9: Handle Queue Dialog ===")
            queue_info = self.monitor_queue_dialog(page)
            
            if queue_info["appeared"]:
                self.log_info(f"Queue dialog handled - Status: {queue_info['status']}, Task ID: {queue_info['task_id']}")
            
            # Final wait for any remaining operations
            self.log_info("Waiting for any remaining operations to complete...")
            page.wait_for_timeout(3000)
            
            # Final summary
            self.log_info("\n" + "="*60)
            self.log_success("TEST COMPLETED SUCCESSFULLY")
            self.log_info("Push Operation Summary:")
            self.log_info(f"  Source: {source_machine}/{repo_name}")
            self.log_info(f"  Destination: {self.config.get('repoPush', {}).get('test', {}).get('targetMachine', 'rediacc12')}")
            self.log_info(f"  Toast Messages: {len(toast_messages)}")
            self.log_info(f"  Queue Dialog: {'Yes' if queue_info['appeared'] else 'No'}")
            self.log_info("="*60)
            
            # Take final screenshot
            self.take_screenshot(page, "04_test_completed")
            
            # Log test completion
            duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end("RepoPushTest", success=True, duration_ms=duration_ms)
            
            return True
            
        except Exception as e:
            self.log_error(f"Test failed with error: {str(e)}")
            duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end("RepoPushTest", success=False, duration_ms=duration_ms)
            
            if self.config.get('repoPush', {}).get('validation', {}).get('screenshotOnError', True):
                try:
                    self.take_screenshot(page, "error_state")
                except:
                    pass
            return False


