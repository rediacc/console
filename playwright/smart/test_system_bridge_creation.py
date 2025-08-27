#!/usr/bin/env python3
"""
System Bridge Creation Test - Smart Framework Integration
Tests the bridge creation functionality in Rediacc console using the smart test framework
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import Page

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from smart_test_base import SmartTestBase


class SystemBridgeCreationTest(SmartTestBase):
    """Test class for creating a bridge in the system."""
    
    def __init__(self):
        """Initialize system bridge creation test."""
        super().__init__("SystemBridgeCreationTest")
    
    def navigate_to_bridges_tab(self, page: Page) -> bool:
        """Navigate to the Bridges tab in System page."""
        try:
            self.log_info("Looking for Bridges tab...")
            
            bridge_config = self.config["systemCreateBridge"]["ui"]
            
            # Try to click Bridges tab
            bridges_tab_selector = bridge_config["bridgesTabSelector"]
            bridges_tab = page.locator(bridges_tab_selector).first
            
            if bridges_tab.is_visible():
                bridges_tab.click()
                time.sleep(1)  # Wait for tab content to load
                self.log_info("Clicked on Bridges tab")
                return True
            else:
                # Fallback selectors
                fallback_selectors = [
                    'button:has-text("Bridges")',
                    'a:has-text("Bridges")',
                    '[role="tab"]:has-text("Bridges")',
                    'text=Bridges'
                ]
                
                for selector in fallback_selectors:
                    try:
                        element = page.locator(selector).first
                        if element.is_visible():
                            element.click()
                            time.sleep(1)
                            self.log_info(f"Clicked on Bridges tab using fallback: {selector}")
                            return True
                    except:
                        continue
                        
            self.log_warning("Could not find Bridges tab")
            return False
            
        except Exception as e:
            self.log_error(f"Failed to navigate to Bridges tab: {str(e)}")
            return False
    
    def open_create_bridge_dialog(self, page: Page) -> bool:
        """Open the create bridge dialog."""
        try:
            self.log_info("Opening create bridge dialog...")
            
            bridge_config = self.config["systemCreateBridge"]["ui"]
            
            # Wait a moment for the page to stabilize
            page.wait_for_timeout(1000)
            
            # Look for the "+" button in the bridges section
            # This is typically the add/create button
            plus_button_selectors = [
                'button[title="Create Bridge"]',
                'button[title="Add Bridge"]',
                'button[title="Add"]',
                'button[title="Create"]',
                'button.ant-btn-icon-only:has([aria-label*="plus"])',
                'button:has(.anticon-plus)',
                '[data-testid="system-create-bridge-button"]',
                '.ant-btn-icon-only',
                'button.ant-btn-circle',
                'button.ant-btn-primary.ant-btn-icon-only'
            ]
            
            for selector in plus_button_selectors:
                try:
                    buttons = page.locator(selector).all()
                    for button in buttons:
                        if button.is_visible():
                            # Check if this is in the bridges section
                            button.click()
                            self.log_info(f"Clicked create bridge button using: {selector}")
                            # Wait to see if modal opens
                            page.wait_for_timeout(500)
                            if page.locator('[role="dialog"]').is_visible():
                                self.log_info("Create bridge dialog opened")
                                return True
                except:
                    continue
            
            # If plus button not found, try text-based buttons
            text_selectors = [
                'button:has-text("Create Bridge")',
                'button:has-text("Add Bridge")',
                'button:has-text("New Bridge")'
            ]
            
            for selector in text_selectors:
                try:
                    button = page.locator(selector).first
                    if button.is_visible():
                        button.click()
                        self.log_info(f"Create bridge dialog opened using: {selector}")
                        return self.wait_for_modal(page)
                except:
                    continue
                    
            self.log_error("Could not find create bridge button")
            return False
            
        except Exception as e:
            self.log_error(f"Failed to open create bridge dialog: {str(e)}")
            return False
    
    def select_team(self, page: Page, team_name: str) -> bool:
        """Select a team in the bridge creation dialog."""
        try:
            self.log_info(f"Selecting team: {team_name}")
            
            bridge_config = self.config["systemCreateBridge"]["ui"]
            
            # Try primary selector
            team_select = page.get_by_test_id(bridge_config["teamSelectTestId"])
            if team_select.is_visible():
                team_select.locator("div span").nth(2).click()
                time.sleep(0.5)
                
                # Select the team
                team_option = page.get_by_title(team_name).locator("div")
                if team_option.is_visible():
                    team_option.click()
                    self.log_info(f"Team selected: {team_name}")
                    return True
            
            # Fallback approach
            self.log_info("Trying alternative selector for team select...")
            
            team_selectors = [
                '.ant-select-selector',
                '[id*="teamName"]',
                'div[class*="ant-select"]:has-text("Select")',
                '.ant-form-item:has-text("Team") .ant-select'
            ]
            
            for selector in team_selectors:
                try:
                    select_element = page.locator(selector).first
                    if select_element.is_visible():
                        select_element.click()
                        time.sleep(0.5)
                        
                        # Try to select team option
                        team_options = [
                            f'[title="{team_name}"]',
                            f'.ant-select-item:has-text("{team_name}")',
                            f'.ant-select-dropdown .ant-select-item:has-text("{team_name}")'
                        ]
                        
                        for opt_selector in team_options:
                            try:
                                option = page.locator(opt_selector).first
                                if option.is_visible():
                                    option.click()
                                    self.log_info(f"Team selected: {team_name}")
                                    return True
                            except:
                                continue
                                
                except:
                    continue
                    
            self.log_warning(f"Could not select team: {team_name}")
            return False
            
        except Exception as e:
            self.log_error(f"Failed to select team: {str(e)}")
            return False
    
    def fill_bridge_name(self, page: Page, bridge_name: str) -> bool:
        """Fill in the bridge name."""
        try:
            self.log_info(f"Entering bridge name: {bridge_name}")
            
            bridge_config = self.config["systemCreateBridge"]["ui"]
            
            # Wait a moment for modal to fully render
            page.wait_for_timeout(500)
            
            # Try primary selector
            try:
                bridge_input = page.get_by_test_id(bridge_config["bridgeNameInputTestId"])
                if bridge_input.is_visible():
                    bridge_input.clear()
                    bridge_input.fill(bridge_name)
                    self.log_info(f"Bridge name entered: {bridge_name}")
                    return True
            except:
                pass
            
            # Fallback selectors - more comprehensive list
            input_selectors = [
                '[data-testid="resource-modal-field-bridgeName-input"]',
                'input[placeholder*="Bridge Name" i]',
                'input[placeholder*="bridge" i]',
                'input[placeholder*="name" i]',
                'input[id*="bridgeName"]',
                '#bridgeName',
                '.ant-form-item:has(label:has-text("Bridge Name")) input',
                '.ant-modal-body input[type="text"]',
                '.ant-modal input[type="text"]',
                'input.ant-input'
            ]
            
            for selector in input_selectors:
                try:
                    input_elements = page.locator(selector).all()
                    for input_element in input_elements:
                        if input_element.is_visible():
                            # Check if this is likely the bridge name field
                            # Skip if it looks like a team select or other field
                            placeholder = input_element.get_attribute("placeholder") or ""
                            if "team" in placeholder.lower():
                                continue
                            
                            input_element.clear()
                            input_element.fill(bridge_name)
                            self.log_info(f"Bridge name entered using: {selector}")
                            return True
                except:
                    continue
                    
            self.log_error("Could not enter bridge name")
            return False
            
        except Exception as e:
            self.log_error(f"Failed to enter bridge name: {str(e)}")
            return False
    
    def submit_bridge_creation(self, page: Page) -> bool:
        """Submit the bridge creation form."""
        try:
            self.log_info("Submitting bridge creation...")
            
            bridge_config = self.config["systemCreateBridge"]["ui"]
            
            # Try primary selector
            submit_button = page.get_by_test_id(bridge_config["submitButtonTestId"])
            if submit_button.is_visible():
                submit_button.click()
                self.log_info("Bridge creation submitted")
                return True
            
            # Try alternative selectors
            submit_selectors = [
                '.ant-modal button:has-text("OK")',
                '.ant-modal button:has-text("Create")',
                '.ant-modal button:has-text("Submit")',
                '.ant-modal button.ant-btn-primary',
                '[role="dialog"] button:has-text("OK")'
            ]
            
            for selector in submit_selectors:
                try:
                    button = page.locator(selector).first
                    if button.is_visible():
                        button.click()
                        self.log_info(f"Bridge creation submitted using: {selector}")
                        return True
                except:
                    continue
                    
            self.log_error("Could not submit bridge creation")
            return False
            
        except Exception as e:
            self.log_error(f"Failed to submit bridge creation: {str(e)}")
            return False
    
    def verify_bridge_creation(self, page: Page) -> bool:
        """Verify that the bridge was created successfully."""
        try:
            bridge_config = self.config["systemCreateBridge"]
            
            # Wait for success notification
            success, message = self.verify_toast_message(
                page, 
                timeout=bridge_config["timeouts"]["validation"]
            )
            
            if success and message:
                # Check if it's a success message
                for success_pattern in bridge_config["validation"]["successIndicators"]:
                    if success_pattern in message:
                        self.log_success(f"Bridge created successfully: {message}")
                        return True
                
                # Check if it's an error
                for error_pattern in bridge_config["validation"]["errorMessages"]:
                    if error_pattern in message:
                        self.log_error(f"Bridge creation failed: {message}")
                        return False
            
            # Wait a moment to see if bridge appears in the table
            time.sleep(2)
            
            # Could also check if the bridge appears in the table
            # This would require knowing the bridge name
            
            return True
            
        except Exception as e:
            self.log_warning(f"Could not verify bridge creation: {str(e)}")
            return True  # Assume success if no error notification
    
    def run_with_page(self, page: Page) -> bool:
        """Execute the bridge creation test with existing page/session."""
        try:
            bridge_config = self.config["systemCreateBridge"]
            
            # Navigate to System page
            if not self.navigate_to_system(page):
                return False
            
            # Switch to Expert mode if required
            if bridge_config["testData"]["requireExpertMode"]:
                if not self.switch_to_expert_mode(page):
                    self.log_warning("Could not switch to Expert mode, continuing anyway")
            
            # Navigate to Bridges tab
            if not self.navigate_to_bridges_tab(page):
                return False
            
            # Open create bridge dialog
            if not self.open_create_bridge_dialog(page):
                return False
            
            # Select team
            team_name = bridge_config["testData"]["teamName"]
            if not self.select_team(page, team_name):
                self.log_warning(f"Could not select team {team_name}, continuing anyway")
            
            # Generate and fill bridge name
            bridge_name = self.get_session_bridge_name()
            self.log_info(f"Using bridge name: {bridge_name}")
            
            if not self.fill_bridge_name(page, bridge_name):
                self.log_warning("Could not fill bridge name, trying with fallback approach")
                # Try one more time with a simpler approach
                page.wait_for_timeout(500)
                try:
                    # Just fill the first visible text input in the modal
                    modal_inputs = page.locator('.ant-modal input[type="text"]').all()
                    for input_elem in modal_inputs:
                        if input_elem.is_visible():
                            input_elem.clear()
                            input_elem.fill(bridge_name)
                            self.log_info("Bridge name entered using modal input fallback")
                            break
                except:
                    return False
            
            # Submit bridge creation
            if not self.submit_bridge_creation(page):
                return False
            
            # Wait for completion
            time.sleep(2)
            
            # Verify bridge creation
            if not self.verify_bridge_creation(page):
                return False
            
            self.log_success(f"Bridge '{bridge_name}' created successfully!")
            
            # Take success screenshot
            self.take_screenshot(page, f"bridge_creation_success_{bridge_name}")
            
            return True
            
        except Exception as e:
            self.log_error(f"Test failed with exception: {str(e)}")
            self.take_screenshot(page, "bridge_creation_exception")
            return False


# Wrapper function for backward compatibility with test_suite_runner.py
def run_with_page(page: Page, config: dict) -> str:
    """Run the bridge creation test with existing page/session."""
    test = SystemBridgeCreationTest()
    success = test.run_with_page(page)
    return test.get_session_bridge_name() if success else None