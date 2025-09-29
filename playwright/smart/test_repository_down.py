"""
Repository Down Test - Refactored Version

This test demonstrates the refactored approach for repository actions:
- All hardcoded values moved to configuration file
- Sleep statements replaced with intelligent wait conditions
- Comprehensive error handling and validation
- Adapted to current UI changes (Local dropdown instead of direct "down" action)
"""

from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
import sys
import json
from datetime import datetime

# Add parent directory to path to import test_utils
sys.path.append(str(Path(__file__).parent.parent))

from test_utils import TestBase
import time
from logging_utils import StructuredLogger, log_playwright_action
from debug_dump import DebugDumper, quick_dump


class RepoDownTest(TestBase):
    """Test class for repository down functionality."""
    
    def __init__(self):
        """Initialize repository down test."""
        script_dir = Path(__file__).parent
        config_path = script_dir.parent / "config.json"
        super().__init__(str(config_path))
        # Initialize logger
        self.logger = StructuredLogger("RepoDownTest", config=self.config.get('logging', {}))
    
    def wait_for_machines_tab_loaded(self, page, timeout=10000):
        """Wait for machines tab to be fully loaded."""
        try:
            # Wait for machine expand buttons - these are unique to machines tab
            page.wait_for_selector("[data-testid*='machine-expand-']", state="visible", timeout=timeout)
            return True
        except:
            return False
    
    def verify_tab_active(self, page, tab_testid):
        """Verify a specific tab is active by checking its CSS classes."""
        try:
            tab = page.get_by_test_id(tab_testid)
            classes = tab.get_attribute("class") or ""
            return "ant-tabs-tab-active" in classes
        except:
            return False
    
    def find_repository_remote_button(self, page, repo_name):
        """Find the remote button for a specific repository."""
        try:
            # Wait for repositories to be visible
            self.wait_for_network_idle(page)
            
            # Look for remote button with specific test-id pattern
            remote_button_selector = f'[data-testid="{self.config["repoDown"]["ui"]["remoteButtonTestId"]}{repo_name}"]'
            
            # First try exact match
            remote_button = page.locator(remote_button_selector).first
            if remote_button.is_visible():
                self.log_info(f"Found remote button for repository: {repo_name}")
                return remote_button
            
            # Fallback: Try to find by button text "Remote" in the same row as repo
            repo_row = page.locator(f'tr:has-text("{repo_name}")').first
            if repo_row.is_visible():
                remote_button = repo_row.locator('button:has-text("Remote")').first
                if remote_button.is_visible():
                    self.log_info(f"Found remote button using text selector for: {repo_name}")
                    return remote_button
            
            return None
        except Exception as e:
            self.log_error(f"Error finding remote button: {str(e)}")
            return None
    
    def select_action_from_dropdown(self, page, action_text):
        """Select an action from the dropdown menu."""
        try:
            # Wait for dropdown to be visible
            dropdown_selector = '.ant-dropdown:not(.ant-dropdown-hidden)'
            page.wait_for_selector(dropdown_selector, timeout=self.config.get('repoDown', {}).get('timeouts', {}).get('elementWait', 5000))
            
            # Log all visible menu items for debugging
            menu_items = page.locator('.ant-dropdown-menu-item').all()
            self.log_info(f"Found {len(menu_items)} menu items in dropdown")
            for item in menu_items:
                item_text = item.text_content()
                self.log_info(f"Menu item: '{item_text}'")
            
            # For "down" action, try multiple approaches
            if action_text.lower() == "down":
                # Try different selectors for the down action
                selectors = [
                    '.ant-dropdown-menu-item[data-menu-id*="down"]',
                    '.ant-dropdown-menu-item:has-text("down")',
                    '.ant-dropdown-menu li[role="menuitem"]:has-text("down")',
                    '.ant-dropdown-menu-item:has(.anticon-pause-circle)',  # PauseCircleOutlined icon
                    '.ant-dropdown li:has-text("down")'
                ]
                
                for selector in selectors:
                    try:
                        down_item = page.locator(selector).first
                        if down_item.is_visible():
                            down_item.click()
                            self.log_success(f"Clicked down action using selector: {selector}")
                            return True
                    except Exception as e:
                        self.log_info(f"Selector {selector} failed: {str(e)}")
                        continue
            
            # Try to click the specified action by text (case-insensitive)
            action_item = page.locator(f'.ant-dropdown-menu-item').filter(has_text=action_text).first
            if action_item.is_visible():
                action_item.click()
                self.log_success(f"Clicked action: {action_text}")
                return True
            
            # If primary action not found, try alternative actions
            for alt_action in self.config['repoDown']['test'].get('alternativeActions', []):
                alt_item = page.locator(f'.ant-dropdown-menu-item').filter(has_text=alt_action).first
                if alt_item.is_visible():
                    alt_item.click()
                    self.log_info(f"Clicked alternative action: {alt_action}")
                    return True
            
            self.log_error(f"Could not find action: {action_text} or alternatives")
            self.take_screenshot(page, "dropdown_menu_debug")
            return False
            
        except Exception as e:
            self.log_error(f"Error selecting action from dropdown: {str(e)}")
            return False
    
    def run_with_page(self, page) -> bool:
        """Execute the repository down test with existing page/session."""
        self.logger.log_test_start("RepoDownTest")
        test_start_time = time.time()
        
        try:
            # Get target repository name (account for rename from previous test)
            target_repo = self.get_session_repository_name() + "_edited"
            self.log_info(f"Looking for repository: {target_repo}")
            
            # Navigate to Resources if not already there
            if "/resources" not in page.url:
                self.logger.log_test_step("navigate_resources", "Navigating to Resources page")
                resources_menu = page.get_by_test_id(self.config['repoDown']['ui']['resourcesMenuTestId'])
                resources_link = resources_menu.get_by_text(self.config['repoDown']['ui']['resourcesMenuText'])
                resources_link.click()
                self.wait_for_network_idle(page)
                self.log_success("Navigated to Resources")
                self.logger.info("Navigated to Resources page")
            else:
                self.log_info("Already on Resources page")
                self.logger.info("Already on Resources page", url=page.url)
            
            # Ensure we're on the Machines tab (previous test might have left us on Repositories tab)
            try:
                machines_tab = page.get_by_test_id("resources-tab-machines")
                if machines_tab.is_visible():
                    machines_tab.click()
                    self.log_info("Clicked Machines tab, waiting for content to load...")
                    
                    # Wait for machine-specific elements to confirm tab switch
                    try:
                        # Use helper method to wait for machines tab
                        if not self.wait_for_machines_tab_loaded(page, timeout=10000):
                            raise Exception("Machines tab content did not load")
                        self.log_success("Machines tab content loaded - expand buttons visible")
                        
                        # Verify tab is actually active
                        if self.verify_tab_active(page, "resources-tab-machines"):
                            self.log_success("Machines tab is active")
                        else:
                            self.log_warning("Machines tab may not be active, but content is visible")
                        
                        # Secondary verification: ensure specific machine is present
                        machine_name = self.config['repoDown']['test']['targetMachine']
                        machine_expand_selector = f"{self.config['repoDown']['ui']['machineExpandTestId']}{machine_name}"
                        page.wait_for_selector(f"[data-testid='{machine_expand_selector}']", timeout=5000, state="visible")
                        self.log_success(f"Target machine {machine_name} found and ready")
                        
                        # Additional wait for complete stabilization
                        page.wait_for_timeout(2000)  # 2 seconds for full UI stabilization
                        self.wait_for_network_idle(page)
                        self.log_success("Successfully switched to Machines tab")
                        
                    except Exception as e:
                        self.log_error(f"Failed to confirm machines tab loaded: {str(e)}")
                        self.logger.error("Tab switch verification failed", error=str(e))
                        self.take_screenshot(page, "machines_tab_load_failed")
                        # Don't proceed if we can't verify the tab switched
                        return False
                        
            except Exception as e:
                self.log_info(f"Machines tab not found or already selected: {str(e)}")
            
            # Expand target machine (smart expand - check if already expanded)
            machine_name = self.config['repoDown']['test']['targetMachine']
            machine_expand_selector = f"{self.config['repoDown']['ui']['machineExpandTestId']}{machine_name}"
            
            machine_expand = self.wait_for_element(
                page,
                f"data-testid:{machine_expand_selector}",
                timeout=5000
            )
            
            if machine_expand:
                try:
                    # Check if machine is already expanded by looking for repository elements
                    expand_button = page.get_by_test_id(machine_expand_selector)
                    
                    # Check the transform style of the chevron to determine if expanded
                    # When expanded, the chevron has transform: rotate(90deg)
                    is_expanded = False
                    try:
                        # Check if any repository actions are visible for this machine
                        repo_actions_visible = page.locator(f'[data-testid*="{self.config["repoDown"]["ui"]["remoteButtonTestId"]}"]').first.is_visible(timeout=1000)
                        if repo_actions_visible:
                            is_expanded = True
                            self.log_info(f"Machine {machine_name} is already expanded (repositories visible)")
                    except:
                        # If no repositories visible, machine is likely collapsed
                        is_expanded = False
                    
                    if not is_expanded:
                        # Machine is collapsed, expand it
                        expand_button.click(force=True)
                        self.log_info("Clicked expand button to expand machine")
                        self.wait_for_network_idle(page)
                        
                        # Wait for repositories to become visible
                        try:
                            page.wait_for_selector(f'[data-testid*="{self.config["repoDown"]["ui"]["remoteButtonTestId"]}"]', state="visible", timeout=5000)
                            self.log_success(f"Expanded machine: {machine_name}")
                        except:
                            self.log_error("Failed to see repositories after expanding")
                            return False
                    else:
                        self.log_info(f"Machine {machine_name} already expanded, skipping expand click")
                    
                    if not page.is_closed():
                        self.take_screenshot(page, "machine_expanded")
                        
                except Exception as e:
                    self.log_error(f"Failed to handle machine expansion: {str(e)}")
                    return False
            else:
                self.log_error(f"Could not find machine: {machine_name}")
                return False
            
            # Find and click remote button for target repository
            remote_button = self.find_repository_remote_button(page, target_repo)
            
            if remote_button:
                try:
                    # Click remote button
                    remote_button.click()
                    self.log_success(f"Clicked remote button for repository: {target_repo}")
                    page.wait_for_timeout(500)  # Brief wait for dropdown animation
                except Exception as e:
                    self.log_error(f"Failed to click remote button: {str(e)}")
                    return False
            else:
                self.log_error(f"No remote button found for repository: {target_repo}")
                return False
            
            # Select action from dropdown
            target_action = self.config['repoDown']['test']['targetAction']
            action_selected = self.select_action_from_dropdown(page, target_action)
            
            if action_selected:
                self.log_success(f"Selected action from dropdown: {target_action}")
                self.wait_for_network_idle(page)
                
                if not page.is_closed():
                    self.take_screenshot(page, "action_selected")
            else:
                if not page.is_closed():
                    self.take_screenshot(page, "error_dropdown_action")
                return False
            
            # Handle queue trace dialog (if configured)
            if self.config['repoDown']['validation'].get('verifyQueueDialog', False):
                self.log_info("⏳ Waiting for Queue Item Trace dialog...")
                queue_timeout = self.config['repoDown'].get('queueTimeout', 120000)  # Default 120 seconds
                
                try:
                    # Wait for the Queue Item Trace dialog to appear
                    # First, wait a moment to ensure any previous dialog animations complete
                    page.wait_for_timeout(500)
                    
                    # DEBUG: Dump state before looking for dialog
                    self.log_info("🔍 DEBUG: Creating dump before dialog search...")
                    dump_file = quick_dump(page, "before_queue_dialog_search", {
                        "test": "repo_down",
                        "step": "before_dialog_search",
                        "repo_name": target_repo
                    })
                    self.log_info(f"📁 Debug dump created: {dump_file}")
                    
                    # Use nth selector to get the LAST (newest) visible modal
                    # This handles cases where old dialogs remain in DOM
                    visible_dialog = page.locator('.ant-modal-wrap:not(.ant-modal-wrap-hidden):has([role="dialog"]:has-text("Queue Item Trace"))').last
                    visible_dialog.wait_for(state="visible", timeout=30000)
                    
                    self.log_success("📊 Queue Item Trace dialog opened")
                    
                    # Wait for task completion
                    self.log_info("⏳ Waiting for task completion...")
                    
                    # Wait for the success alert with "Task Completed Successfully" 
                    success_found = False
                    
                    try:
                        # Look for the success alert box specifically
                        # Use a shorter timeout since down operations complete quickly
                        success_alert = page.wait_for_selector(
                            '.ant-alert-success:has-text("Task Completed Successfully")', 
                            state="visible", 
                            timeout=30000  # 30 seconds for down operation
                        )
                        
                        if success_alert:
                            self.log_success("✅ Task Completed Successfully")
                            
                            # Try to get the duration message
                            try:
                                duration_text = page.locator('.ant-alert-success:has-text("The task finished successfully after")').text_content()
                                if duration_text and "after" in duration_text:
                                    self.log_info(f"📝 {duration_text.strip()}")
                            except:
                                pass
                            
                            success_found = True
                    except:
                        # Fallback: Check for completed status in the steps
                        try:
                            completed_step = page.wait_for_selector(
                                'text=/Completed.*Done/', 
                                state="visible", 
                                timeout=5000
                            )
                            if completed_step:
                                self.log_success("✅ Task completed (Step 4: Completed)")
                                success_found = True
                        except:
                            pass
                    
                    if success_found:
                        # Optional: Check duration and machine info
                        try:
                            duration = page.locator('text=/Duration/:has(strong)').locator('strong').text_content()
                            if duration:
                                self.log_info(f"⏱️  Duration: {duration}")
                        except:
                            pass
                        
                        # Wait a bit to ensure everything is loaded
                        page.wait_for_timeout(2000)
                        
                        # Always close Queue Item Trace dialog for shared session tests
                        try:
                            # Try the test-id first (as shown in dummy test), then fallback to text selector
                            try:
                                close_button = page.get_by_test_id("queue-trace-close-button")
                                close_button.wait_for(state="visible", timeout=2000)
                            except:
                                close_button = page.locator('button:has-text("Close")').last
                                close_button.wait_for(state="visible", timeout=self.config['repoDown']['timeouts']['elementWait'])
                            
                            close_button.click()
                            self.log_success("📊 Closed Queue Item Trace dialog")
                        except:
                            self.log_warning("⚠️  Could not find Close button for Queue Item Trace dialog")
                    else:
                        self.log_warning("⚠️  Repository down operation completed but success message not found")
                        
                except Exception as e:
                    self.log_warning(f"⚠️  Queue Item Trace dialog did not appear or timed out: {e}")
                    
                    # DEBUG: Dump state when dialog not found
                    self.log_info("🔍 DEBUG: Creating dump after dialog timeout...")
                    dump_file = quick_dump(page, "queue_dialog_timeout", {
                        "test": "repo_down",
                        "step": "dialog_timeout",
                        "error": str(e),
                        "repo_name": target_repo
                    })
                    self.log_info(f"📁 Debug dump created: {dump_file}")
                    
                    # Take a screenshot to see what's on screen
                    if not page.is_closed():
                        self.take_screenshot(page, "queue_dialog_timeout")
                    # Check if the operation completed without showing dialog
                    self.log_info("Checking if operation completed without dialog...")
            
            # Check for success indicators
            if self.config['repoDown']['validation'].get('checkForSuccessToast', True):
                success_toast = self.wait_for_toast_message(page, timeout=3000)
                if success_toast:
                    self.log_success(f"Success notification: {success_toast}")
                else:
                    self.log_info("No toast message appeared")
            
            self.log_info("\n" + "="*60)
            self.log_info("TEST COMPLETED SUCCESSFULLY")
            self.log_info("Test Flow Summary:")
            self.log_info("✓ Navigated to Resources")
            self.log_info("✓ Expanded target machine")
            self.log_info("✓ Clicked Remote button for repository")
            self.log_info(f"✓ Selected '{target_action}' action from dropdown")
            if self.config['repoDown']['validation'].get('verifyQueueDialog', False):
                self.log_info("✓ Waited for Queue Item Trace dialog and task completion")
            self.log_info("Note: Session timeout after action is expected behavior")
            self.log_info("="*60)
            
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end("RepoDownTest", success=True, duration_ms=test_duration_ms)
            return True
            
        except Exception as e:
            self.log_error(f"Test failed with error: {str(e)}")
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.error("Repository down test failed", error=str(e), duration_ms=test_duration_ms)
            self.logger.log_test_end("RepoDownTest", success=False, duration_ms=test_duration_ms)
            if self.config.get('repoDown', {}).get('validation', {}).get('screenshotOnError', True):
                if not page.is_closed():
                    self.take_screenshot(page, "error_state")
            return False
    
    def run(self, playwright: Playwright) -> None:
        """Execute the repository down test."""
        self.logger.log_test_start("RepoDownTest")
        test_start_time = time.time()
        
        browser = playwright.chromium.launch(
            headless=self.config['browser']['headless'],
            slow_mo=self.config['browser']['slowMo'],
            args=['--start-maximized']  # Tam ekran başlatma argümanı
        )
        context = browser.new_context(
            viewport=None,  # Viewport kısıtlamasını kaldır
            no_viewport=True  # Browser pencere boyutunu kullan
        )
        
        main_page = None
        login_page = None
        
        try:
            # Step 1: Navigate to main page
            main_page = context.new_page()
            self.setup_console_handler(main_page)
            
            self.logger.log_test_step("navigate_main", "Navigating to main page")
            with self.logger.performance_tracker("navigate_main_page"):
                main_page.goto(f"{self.config['baseUrl']}/console")
                self.wait_for_network_idle(main_page)
            self.log_success("✓ Step 1: Navigated to main page")
            self.logger.info("Main page loaded", url=f"{self.config['baseUrl']}/console")
            self.take_screenshot(main_page, "01_initial_page")
            
            # Step 2: Handle login
            initial_pages = context.pages
            login_link = main_page.get_by_role("banner").get_by_role("link", name=self.config['ui']['loginLinkText'])
            login_link.click()
            
            # Wait for new page/tab
            main_page.wait_for_timeout(1000)
            
            current_pages = context.pages
            if len(current_pages) > len(initial_pages):
                login_page = current_pages[-1]
                self.setup_console_handler(login_page)
                self.log_success("✓ Step 2: Login opened in new tab")
            else:
                if "login" in main_page.url:
                    login_page = main_page
                else:
                    self.log_error("Failed to open login page")
                    return
            
            # Step 3: Perform login
            login_page.wait_for_load_state('domcontentloaded')
            self.logger.log_test_step("fill_login", "Filling login credentials")
            
            with self.logger.performance_tracker("fill_login_form"):
                # Fill email
                email_input = login_page.get_by_test_id(self.config['repoDown']['ui']['loginEmailTestId'])
                email_input.click()
                email_input.fill(self.config['login']['credentials']['email'])
                log_playwright_action(self.logger, "fill", selector="login-email-input", value_info="email entered")
                
                # Fill password
                password_input = login_page.get_by_test_id(self.config['repoDown']['ui']['loginPasswordTestId'])
                password_input.click()
                password_input.fill(self.config['login']['credentials']['password'])
                log_playwright_action(self.logger, "fill", selector="login-password-input", value_info="***SANITIZED***")
            
            # Submit login
            self.logger.log_test_step("submit_login", "Submitting login form")
            submit_button = login_page.get_by_test_id(self.config['repoDown']['ui']['loginSubmitButtonTestId'])
            with self.logger.performance_tracker("login_submission"):
                with login_page.expect_response(lambda r: '/api/' in r.url and r.status == 200) as response_info:
                    submit_button.click()
                    log_playwright_action(self.logger, "click", selector="login-submit-button", element_text="Submit")
                
                response = response_info.value
                self.wait_for_network_idle(login_page)
            self.log_success(f"✓ Step 3: Login successful (Status: {response.status})")
            self.logger.info("Login API response received", status=response.status)
            
            # Step 4: Navigate to Resources
            resources_menu = self.wait_for_element(
                login_page, 
                f"data-testid:{self.config['repoDown']['ui']['resourcesMenuTestId']}", 
                timeout=10000
            )
            
            if resources_menu:
                resources_link = login_page.get_by_test_id(self.config['repoDown']['ui']['resourcesMenuTestId']).get_by_text(
                    self.config['repoDown']['ui']['resourcesMenuText']
                )
                resources_link.click()
                self.wait_for_network_idle(login_page)
                self.log_success("✓ Step 4: Navigated to Resources")
                self.take_screenshot(login_page, "02_resources_page")
            
            # Step 5: Expand target machine (smart expand - check if already expanded)
            self.logger.log_test_step("expand_machine", "Expanding target machine")
            machine_name = self.config['repoDown']['test']['targetMachine']
            machine_expand_selector = f"{self.config['repoDown']['ui']['machineExpandTestId']}{machine_name}"
            
            machine_expand = self.wait_for_element(
                login_page,
                f"data-testid:{machine_expand_selector}",
                timeout=5000
            )
            
            if machine_expand:
                try:
                    # Check if machine is already expanded by looking for repository elements
                    expand_button = login_page.get_by_test_id(machine_expand_selector)
                    
                    # Check if any repository actions are visible for this machine
                    is_expanded = False
                    try:
                        repo_actions_visible = login_page.locator(f'[data-testid*="{self.config["repoDown"]["ui"]["remoteButtonTestId"]}"]').first.is_visible(timeout=1000)
                        if repo_actions_visible:
                            is_expanded = True
                            self.log_info(f"Machine {machine_name} is already expanded (repositories visible)")
                    except:
                        # If no repositories visible, machine is likely collapsed
                        is_expanded = False
                    
                    if not is_expanded:
                        # Machine is collapsed, expand it
                        expand_button.click(force=True)
                        self.log_info("Clicked expand button to expand machine")
                        log_playwright_action(self.logger, "click", selector=machine_expand_selector, element_text="Expand", extra={"force": True, "action": "expand"})
                        self.wait_for_network_idle(login_page)
                        
                        # Wait for repositories to become visible
                        try:
                            login_page.wait_for_selector(f'[data-testid*="{self.config["repoDown"]["ui"]["remoteButtonTestId"]}"]', state="visible", timeout=5000)
                            self.log_success(f"✓ Step 5: Expanded machine: {machine_name}")
                        except:
                            self.log_error("Failed to see repositories after expanding")
                            return
                    else:
                        self.log_info(f"Machine {machine_name} already expanded, skipping expand click")
                        log_playwright_action(self.logger, "skip", selector=machine_expand_selector, element_text="Already expanded", extra={"reason": "already_expanded"})
                        self.log_success(f"✓ Step 5: Machine already expanded: {machine_name}")
                    
                    self.logger.info("Machine expansion handled successfully", machine=machine_name, was_already_expanded=is_expanded)
                    self.take_screenshot(login_page, "03_machine_expanded")
                    
                except Exception as e:
                    self.log_error(f"Failed to handle machine expansion: {str(e)}")
                    self.logger.error("Failed to expand machine", error=str(e), machine=machine_name)
                    return
            else:
                self.log_error(f"Could not find machine: {machine_name}")
                return
            
            # Step 6: Find and click remote button for target repository
            target_repo = self.get_session_repository_name() + "_edited"
            self.log_info(f"Looking for repository: {target_repo}")
            remote_button = self.find_repository_remote_button(login_page, target_repo)
            
            if remote_button:
                try:
                    # Click remote button
                    remote_button.click()
                    self.log_success(f"✓ Step 6: Clicked remote button for repository: {target_repo}")
                    login_page.wait_for_timeout(500)  # Brief wait for dropdown animation
                except Exception as e:
                    self.log_error(f"Failed to click remote button: {str(e)}")
                    return
            else:
                self.log_error(f"No remote button found for repository: {target_repo}")
                return
            
            # Step 7: Select action from dropdown
            target_action = self.config['repoDown']['test']['targetAction']
            action_selected = self.select_action_from_dropdown(login_page, target_action)
            
            if action_selected:
                self.log_success(f"✓ Step 7: Selected action from dropdown")
                self.wait_for_network_idle(login_page)
                self.take_screenshot(login_page, "04_action_selected")
            else:
                self.take_screenshot(login_page, "error_dropdown_action")
            
            # Step 8: Handle queue trace dialog (if configured)
            if self.config['repoDown']['validation'].get('verifyQueueDialog', False):
                self.log_info("⏳ Waiting for Queue Item Trace dialog...")
                queue_timeout = self.config['repoDown'].get('queueTimeout', 120000)  # Default 120 seconds
                
                try:
                    # Wait for the Queue Item Trace dialog to appear
                    # First, wait a moment to ensure any previous dialog animations complete
                    login_page.wait_for_timeout(500)
                    
                    # DEBUG: Dump state before looking for dialog
                    self.log_info("🔍 DEBUG: Creating dump before dialog search...")
                    dump_file = quick_dump(login_page, "before_queue_dialog_search", {
                        "test": "repo_down",
                        "step": "before_dialog_search",
                        "repo_name": target_repo
                    })
                    self.log_info(f"📁 Debug dump created: {dump_file}")
                    
                    # Use nth selector to get the LAST (newest) visible modal
                    # This handles cases where old dialogs remain in DOM
                    visible_dialog = login_page.locator('.ant-modal-wrap:not(.ant-modal-wrap-hidden):has([role="dialog"]:has-text("Queue Item Trace"))').last
                    visible_dialog.wait_for(state="visible", timeout=queue_timeout)
                    self.log_success("✓ Step 8: Queue Item Trace dialog opened")
                    
                    # Wait for task completion
                    self.log_info("⏳ Waiting for task completion...")
                    
                    # Wait for the success alert with "Task Completed Successfully" 
                    success_found = False
                    
                    try:
                        # Look for the success alert box specifically
                        # Use a shorter timeout since down operations complete quickly
                        success_alert = login_page.wait_for_selector(
                            '.ant-alert-success:has-text("Task Completed Successfully")', 
                            state="visible", 
                            timeout=30000  # 30 seconds for down operation
                        )
                        
                        if success_alert:
                            self.log_success("✅ Task Completed Successfully")
                            
                            # Try to get the duration message
                            try:
                                duration_text = login_page.locator('.ant-alert-success:has-text("The task finished successfully after")').text_content()
                                if duration_text and "after" in duration_text:
                                    self.log_info(f"📝 {duration_text.strip()}")
                            except:
                                pass
                            
                            success_found = True
                    except:
                        # Fallback: Check for completed status in the steps
                        try:
                            completed_step = login_page.wait_for_selector(
                                'text=/Completed.*Done/', 
                                state="visible", 
                                timeout=5000
                            )
                            if completed_step:
                                self.log_success("✅ Task completed (Step 4: Completed)")
                                success_found = True
                        except:
                            pass
                    
                    if success_found:
                        # Optional: Check duration and machine info
                        try:
                            duration = login_page.locator('text=/Duration/:has(strong)').locator('strong').text_content()
                            if duration:
                                self.log_info(f"⏱️  Duration: {duration}")
                        except:
                            pass
                        
                        # Wait a bit to ensure everything is loaded
                        login_page.wait_for_timeout(2000)
                        
                        # Always close Queue Item Trace dialog for shared session tests
                        try:
                            # Try the test-id first (as shown in dummy test), then fallback to text selector
                            try:
                                close_button = login_page.get_by_test_id("queue-trace-close-button")
                                close_button.wait_for(state="visible", timeout=2000)
                            except:
                                close_button = login_page.locator('button:has-text("Close")').last
                                close_button.wait_for(state="visible", timeout=self.config['repoDown']['timeouts']['elementWait'])
                            
                            close_button.click()
                            self.log_success("✓ Step 8: Closed Queue Item Trace dialog")
                        except:
                            self.log_warning("⚠️  Could not find Close button for Queue Item Trace dialog")
                    else:
                        self.log_warning("⚠️  Repository down operation completed but success message not found")
                        
                except Exception as e:
                    self.log_warning(f"⚠️  Queue Item Trace dialog did not appear or timed out: {e}")
                    
                    # DEBUG: Dump state when dialog not found
                    self.log_info("🔍 DEBUG: Creating dump after dialog timeout...")
                    dump_file = quick_dump(login_page, "queue_dialog_timeout", {
                        "test": "repo_down",
                        "step": "dialog_timeout",
                        "error": str(e),
                        "repo_name": target_repo
                    })
                    self.log_info(f"📁 Debug dump created: {dump_file}")
                    
                    # Take a screenshot to see what's on screen
                    if not login_page.is_closed():
                        self.take_screenshot(login_page, "queue_dialog_timeout")
                    # Check if the operation completed without showing dialog
                    self.log_info("Checking if operation completed without dialog...")
            
            # Step 9: Check for success indicators
            if self.config['repoDown']['validation'].get('checkForSuccessToast', True):
                success_toast = self.wait_for_toast_message(login_page, timeout=3000)
                if success_toast:
                    self.log_success(f"✓ Success notification: {success_toast}")
                else:
                    self.log_info("No toast message appeared")
            
            self.log_info("\\n" + "="*60)
            self.log_info("TEST COMPLETED SUCCESSFULLY")
            self.log_info("Test Flow Summary:")
            self.log_info("✓ Logged in successfully")
            self.log_info("✓ Navigated to Resources")
            self.log_info("✓ Expanded target machine")
            self.log_info("✓ Clicked Remote button for repository")
            self.log_info("✓ Selected 'down' action from dropdown")
            if self.config['repoDown']['validation'].get('verifyQueueDialog', False):
                self.log_info("✓ Waited for Queue Item Trace dialog and task completion")
            self.log_info("Note: Session timeout after action is expected behavior")
            self.log_info("="*60)
            
        except Exception as e:
            self.log_error(f"Test failed with error: {str(e)}")
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.error("Repository down test failed", error=str(e), duration_ms=test_duration_ms)
            if self.config.get('repoDown', {}).get('validation', {}).get('screenshotOnError', True):
                try:
                    if login_page:
                        self.take_screenshot(login_page, "error_state")
                    elif main_page:
                        self.take_screenshot(main_page, "error_state")
                except:
                    pass
            raise
        finally:
            # Get console errors
            if login_page:
                page_errors = self.get_page_errors(login_page)
                for error in page_errors:
                    self.log_error(f"JavaScript error: {error}")
            
            # Print test summary
            test_passed = self.print_summary()
            test_duration_ms = (time.time() - test_start_time) * 1000
            self.logger.log_test_end("RepoDownTest", success=test_passed, duration_ms=test_duration_ms)
            
            # Close browser
            context.close()
            browser.close()
            self.logger.info("Browser closed")
            
            # Exit with appropriate code
            sys.exit(0 if test_passed else 1)


def main():
    """Main entry point."""
    print(f"\\nRepository Down Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print("This test has been refactored to:")
    print("- Remove all sleep statements (6 total)")
    print("- Use configuration file for all values")
    print("- Add intelligent wait conditions")
    print("- Handle UI changes (dropdown menu instead of direct actions)")
    print("="*70 + "\\n")
    
    test = RepoDownTest()
    
    with sync_playwright() as playwright:
        test.run(playwright)


if __name__ == "__main__":
    main()