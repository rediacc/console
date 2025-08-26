#!/usr/bin/env python3
"""
System Create Region Test - Smart Version
Tests the region creation functionality in Rediacc console
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class CreateRegionTest:
    """Smart region creation test with config-based approach"""
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        self.config_path = config_path or Path(__file__).parent / "config.json"
        self.config = self.load_config()
        self.page = None
        self.context = None
        self.browser = None
        # Generate unique region name with timestamp
        self.region_name = f"region_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def load_config(self) -> dict:
        """Load configuration from config.json"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Add default region config if not present
                if 'systemCreateRegion' not in config:
                    config['systemCreateRegion'] = {
                        "ui": {
                            "systemNavTestId": "main-nav-system",
                            "regionsTabSelector": '[role="tab"]:has-text("Regions")',
                            "createRegionButtonTestId": "system-create-region-button",
                            "regionNameInputTestId": "resource-modal-field-regionName-input",
                            "regionCodeInputTestId": "resource-modal-field-regionCode-input",
                            "locationInputTestId": "resource-modal-field-location-input",
                            "submitButtonTestId": "resource-modal-ok-button",
                            "cancelButtonTestId": "resource-modal-cancel-button",
                            "modalSelector": ".ant-modal",
                            "regionsTableSelector": "table.ant-table"
                        },
                        "testData": {
                            "regionNamePrefix": "region",
                            "generateUniqueName": True,
                            "regionCode": None,
                            "location": None,
                            "requireExpertMode": True
                        },
                        "validation": {
                            "successIndicators": [
                                "Region created successfully",
                                "Region '.*' created successfully",
                                "Successfully created region"
                            ],
                            "errorMessages": [
                                "Region already exists",
                                "Region name is required",
                                "Invalid region configuration"
                            ],
                            "notificationSelectors": [
                                ".ant-message",
                                ".ant-notification",
                                "[role='alert']"
                            ],
                            "checkTableEntry": True
                        },
                        "timeouts": {
                            "navigation": 10000,
                            "element": 5000,
                            "modalOpen": 3000,
                            "creation": 5000,
                            "validation": 5000
                        }
                    }
                return config
        except FileNotFoundError:
            print(f"Config file not found at {self.config_path}")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Invalid JSON in config file {self.config_path}")
            sys.exit(1)
    
    def wait_for_element(self, selector: str, timeout: int = None):
        """Smart wait for element - waits only as long as needed"""
        timeout = timeout or self.config['timeouts']['elementVisible']
        try:
            element = self.page.locator(selector).first
            element.wait_for(state="visible", timeout=timeout)
            return element
        except:
            return None
    
    def smart_click(self, element_or_selector, timeout: int = None):
        """Smart click that waits for element to be ready"""
        timeout = timeout or self.config['timeouts']['elementVisible']
        
        if isinstance(element_or_selector, str):
            element = self.wait_for_element(element_or_selector, timeout)
            if element:
                element.click()
                return True
        else:
            try:
                element_or_selector.wait_for(state="visible", timeout=timeout)
                element_or_selector.click()
                return True
            except:
                pass
        return False
    
    def smart_fill(self, selector: str, value: str, timeout: int = None):
        """Smart fill that waits for input to be ready"""
        element = self.wait_for_element(selector, timeout)
        if element:
            element.fill(value)
            return True
        return False
    
    def login(self):
        """Login to the console using config credentials"""
        print("Logging in...")
        
        # Navigate to console
        base_url = self.config['baseUrl']
        self.page.goto(f"{base_url}/console")
        self.page.wait_for_load_state("domcontentloaded")
        
        # Check if already on login page
        current_url = self.page.url
        if '/login' not in current_url and 'signin' not in current_url:
            # Try to find login link
            login_selectors = [
                '[data-testid="header-login-link"]',
                'a:has-text("Login")',
                '[role="banner"] a:has-text("Login")'
            ]
            
            for selector in login_selectors:
                try:
                    login_link = self.page.locator(selector).first
                    if login_link.is_visible():
                        # Handle potential popup
                        with self.page.expect_popup() as popup_info:
                            login_link.click()
                            self.page = popup_info.value
                        break
                except:
                    # No popup, continue with same page
                    if self.smart_click(selector, timeout=2000):
                        break
        
        # Wait for login form
        self.page.wait_for_load_state("networkidle", timeout=5000)
        
        # Fill login credentials from config
        email = self.config['login']['credentials']['email']
        password = self.config['login']['credentials']['password']
        
        # Try multiple email input selectors
        email_selectors = [
            '[data-testid="login-email-input"]',
            'input[type="email"]',
            'input[placeholder*="email" i]',
            'input[name="email"]'
        ]
        
        for selector in email_selectors:
            if self.smart_fill(selector, email, timeout=2000):
                break
        
        # Try multiple password input selectors
        password_selectors = [
            '[data-testid="login-password-input"]',
            'input[type="password"]',
            'input[placeholder*="password" i]'
        ]
        
        for selector in password_selectors:
            if self.smart_fill(selector, password, timeout=2000):
                break
        
        # Submit login
        submit_selectors = [
            '[data-testid="login-submit-button"]',
            'button[type="submit"]',
            'button:has-text("Sign In")',
            'button:has-text("Login")'
        ]
        
        for selector in submit_selectors:
            if self.smart_click(selector, timeout=2000):
                break
        
        # Wait for dashboard
        try:
            self.page.wait_for_url("**/console/dashboard", timeout=self.config['login']['timeouts']['navigation'])
            print("Login successful!")
            return True
        except:
            print("Login failed - timeout waiting for dashboard")
            return False
    
    def navigate_to_system(self):
        """Navigate to System page"""
        print("Navigating to System...")
        
        system_selectors = [
            '[data-testid="main-nav-system"]',
            'nav a:has-text("System")',
            'a[href*="/system"]',
            '[data-testid*="system"]',
            'text=System'
        ]
        
        for selector in system_selectors:
            if self.smart_click(selector, timeout=2000):
                self.page.wait_for_load_state("networkidle", timeout=5000)
                return True
        
        return False
    
    def switch_to_expert_mode(self):
        """Switch to Expert mode if needed"""
        print("Checking for Expert mode...")
        
        # Check if Regions tab or section is already visible (indicates Expert mode)
        regions_visible = self.page.locator('[role="tab"]:has-text("Regions")').is_visible() or \
                         self.page.locator('.ant-tabs-tab:has-text("Regions")').is_visible() or \
                         self.page.locator('text="Regions & Infrastructure"').is_visible()
        
        if regions_visible:
            print("Regions section already visible (Expert mode active)")
            return True
        
        # Try to switch to Expert mode
        expert_selectors = [
            'label:has-text("Expert")',
            '.ant-radio-wrapper:has-text("Expert")',
            'input[type="radio"][value="expert"]',
            'span:has-text("Expert")',
            '[role="radio"]:has-text("Expert")'
        ]
        
        for selector in expert_selectors:
            element = self.page.locator(selector).first
            if element.is_visible():
                # Check if not already selected
                try:
                    is_checked = element.is_checked() if element.get_attribute("type") == "radio" else False
                except:
                    is_checked = False
                
                if not is_checked:
                    element.click()
                    # Wait for UI to update
                    self.page.wait_for_load_state("networkidle", timeout=3000)
                    print("Switched to Expert mode")
                else:
                    print("Already in Expert mode")
                return True
        
        print("Could not find Expert mode selector")
        return False
    
    def navigate_to_regions_section(self):
        """Navigate to Regions section"""
        print("Looking for Regions section...")
        
        # Get config
        region_config = self.config.get('systemCreateRegion', {})
        ui_config = region_config.get('ui', {})
        
        # Try Regions tab first
        regions_tab_selectors = [
            ui_config.get('regionsTabSelector', '[role="tab"]:has-text("Regions")'),
            '.ant-tabs-tab:has-text("Regions")',
            'button:has-text("Regions")',
            'a:has-text("Regions")',
            'text=Regions'
        ]
        
        for selector in regions_tab_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for content to load
                self.page.wait_for_load_state("networkidle", timeout=3000)
                print("Regions tab/section opened")
                return True
        
        # Check if already in regions section (might be visible without clicking)
        if self.page.locator('text="Regions & Infrastructure"').is_visible():
            print("Already in Regions section")
            return True
        
        print("Could not find Regions section")
        return False
    
    def open_create_region_dialog(self):
        """Open the create region dialog"""
        print("Opening create region dialog...")
        
        # Get config
        region_config = self.config.get('systemCreateRegion', {})
        ui_config = region_config.get('ui', {})
        
        # Try test-id first
        create_button_id = ui_config.get('createRegionButtonTestId', 'system-create-region-button')
        if self.smart_click(f'[data-testid="{create_button_id}"]', timeout=2000):
            print("Create region dialog opened")
            return True
        
        # Try alternative selectors
        create_selectors = [
            'button:has-text("Create Region")',
            'button:has-text("Add Region")',
            'button:has-text("New Region")',
            'button:has-text("Create")',
            'button:has-text("Add")',
            'button[title*="Create"]',
            'button[title*="Add"]',
            'button.ant-btn-primary:has-text("+")',
            '.ant-btn-icon-only:has([aria-label*="plus"])',
            'button.ant-btn-primary',
            '[data-testid*="create"]',
            '[data-testid*="add"]'
        ]
        
        for selector in create_selectors:
            if self.smart_click(selector, timeout=2000):
                # Wait for modal to appear
                self.page.wait_for_timeout(500)
                print("Create region dialog opened")
                return True
        
        print("Could not open create region dialog")
        return False
    
    def fill_region_form(self):
        """Fill the region creation form"""
        print(f"Filling region form with name: {self.region_name}...")
        
        # Get config
        region_config = self.config.get('systemCreateRegion', {})
        ui_config = region_config.get('ui', {})
        test_data = region_config.get('testData', {})
        
        # Fill region name
        region_name_id = ui_config.get('regionNameInputTestId', 'resource-modal-field-regionName-input')
        name_filled = False
        
        if self.smart_fill(f'[data-testid="{region_name_id}"]', self.region_name, timeout=2000):
            name_filled = True
        else:
            # Try alternative selectors
            name_selectors = [
                'input[placeholder*="region" i]',
                'input[placeholder*="name" i]',
                'input[id*="regionName"]',
                '.ant-form-item:has-text("Region Name") input',
                '.ant-modal input[type="text"]:first'
            ]
            
            for selector in name_selectors:
                if self.smart_fill(selector, self.region_name, timeout=1000):
                    name_filled = True
                    break
        
        if name_filled:
            print(f"Region name entered: {self.region_name}")
        else:
            print("Could not enter region name")
            return False
        
        # Fill region code if provided
        region_code = test_data.get('regionCode')
        if region_code:
            region_code_id = ui_config.get('regionCodeInputTestId', 'resource-modal-field-regionCode-input')
            if self.smart_fill(f'[data-testid="{region_code_id}"]', region_code, timeout=1000):
                print(f"Region code entered: {region_code}")
            else:
                code_selectors = [
                    'input[placeholder*="code" i]',
                    'input[id*="regionCode"]',
                    '.ant-form-item:has-text("Region Code") input'
                ]
                for selector in code_selectors:
                    if self.smart_fill(selector, region_code, timeout=500):
                        print(f"Region code entered: {region_code}")
                        break
        
        # Fill location if provided
        location = test_data.get('location')
        if location:
            location_id = ui_config.get('locationInputTestId', 'resource-modal-field-location-input')
            if self.smart_fill(f'[data-testid="{location_id}"]', location, timeout=1000):
                print(f"Location entered: {location}")
            else:
                location_selectors = [
                    'input[placeholder*="location" i]',
                    'input[id*="location"]',
                    '.ant-form-item:has-text("Location") input'
                ]
                for selector in location_selectors:
                    if self.smart_fill(selector, location, timeout=500):
                        print(f"Location entered: {location}")
                        break
        
        # Click somewhere in modal to dismiss any validation popups
        try:
            modal_body = self.page.locator('.ant-modal-body').first
            if modal_body.is_visible():
                modal_body.click()
        except:
            pass
        
        return name_filled
    
    def submit_region_creation(self):
        """Submit the region creation form"""
        print("Submitting region creation...")
        
        # Get config
        region_config = self.config.get('systemCreateRegion', {})
        ui_config = region_config.get('ui', {})
        
        # Try test-id first
        submit_id = ui_config.get('submitButtonTestId', 'resource-modal-ok-button')
        if self.smart_click(f'[data-testid="{submit_id}"]', timeout=2000):
            print("Region creation submitted")
            return True
        
        # Try alternative selectors
        submit_selectors = [
            '.ant-modal button:has-text("OK")',
            '.ant-modal button:has-text("Create")',
            '.ant-modal button:has-text("Submit")',
            '.ant-modal button.ant-btn-primary',
            '[role="dialog"] button[type="submit"]',
            '[role="dialog"] button:has-text("OK")',
            '[role="dialog"] button.ant-btn-primary'
        ]
        
        for selector in submit_selectors:
            if self.smart_click(selector, timeout=2000):
                print("Region creation submitted")
                return True
        
        print("Could not submit region creation")
        return False
    
    def check_success_notification(self):
        """Check for success notification"""
        print("Checking for success notification...")
        
        # Get config
        region_config = self.config.get('systemCreateRegion', {})
        validation = region_config.get('validation', {})
        notification_selectors = validation.get('notificationSelectors', [
            '.ant-message',
            '.ant-notification',
            '[role="alert"]'
        ])
        
        for selector in notification_selectors:
            element = self.page.locator(selector).first
            if element.is_visible():
                message = element.text_content()
                print(f"Notification found: {message}")
                
                # Check if it's a success message
                success_indicators = validation.get('successIndicators', [])
                for indicator in success_indicators:
                    if indicator.replace('.*', '').lower() in message.lower():
                        print(f"Success: {message}")
                        return True
                
                # Check for generic success
                if 'success' in message.lower() or 'created' in message.lower():
                    print(f"Success: {message}")
                    return True
                
                # Check for errors
                error_messages = validation.get('errorMessages', [])
                for error in error_messages:
                    if error.lower() in message.lower():
                        print(f"Error: {message}")
                        return False
        
        return False
    
    def verify_region_in_table(self):
        """Verify the region appears in the regions table"""
        print(f"Verifying region '{self.region_name}' in table...")
        
        # Wait for table to update
        self.page.wait_for_timeout(1000)
        
        # Check if region appears in table
        try:
            region_element = self.page.locator(f'text="{self.region_name}"').first
            if region_element.is_visible():
                print(f"Region '{self.region_name}' found in table")
                return True
        except:
            pass
        
        print(f"Could not verify region '{self.region_name}' in table")
        return False
    
    def take_screenshot(self, name: str):
        """Take a screenshot with timestamp"""
        screenshots_dir = Path(self.config.get('screenshots', {}).get('path', './artifacts/screenshots'))
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        screenshot_path = screenshots_dir / f"{name}.png"
        self.page.screenshot(path=str(screenshot_path))
        print(f"Screenshot saved: {screenshot_path}")
    
    def run(self, playwright: Playwright):
        """Main test execution"""
        try:
            print("Starting System Create Region Test (Smart Version)...")
            print(f"Region name to be created: {self.region_name}")
            
            # Launch browser based on config
            browser_config = self.config.get('browser', {})
            self.browser = playwright.chromium.launch(
                headless=browser_config.get('headless', False),
                slow_mo=browser_config.get('slowMo', 0)
            )
            
            # Create context with viewport
            viewport = browser_config.get('viewport', {})
            self.context = self.browser.new_context(
                viewport={
                    'width': viewport.get('width', 1280),
                    'height': viewport.get('height', 720)
                }
            )
            
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.config['timeouts']['pageLoad'])
            
            # Execute test steps
            if not self.login():
                raise Exception("Login failed")
            
            if not self.navigate_to_system():
                raise Exception("Could not navigate to System")
            
            # Take screenshot before mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("createregion_before_expert")
            
            if not self.switch_to_expert_mode():
                print("Warning: Could not switch to Expert mode, continuing...")
            
            # Take screenshot after mode switch
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("createregion_after_expert")
            
            if not self.navigate_to_regions_section():
                print("Warning: Could not navigate to Regions section")
            
            # Take screenshot of regions list
            if self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("createregion_regions_list")
            
            if self.open_create_region_dialog():
                # Wait for dialog to fully load
                self.page.wait_for_timeout(500)
                
                # Take screenshot of dialog
                if self.config.get('screenshots', {}).get('enabled', True):
                    self.take_screenshot("createregion_dialog_open")
                
                if self.fill_region_form():
                    # Take screenshot after filling form
                    if self.config.get('screenshots', {}).get('enabled', True):
                        self.take_screenshot("createregion_form_filled")
                    
                    if self.submit_region_creation():
                        # Wait for operation to complete
                        self.page.wait_for_load_state("networkidle", timeout=5000)
                        
                        # Check for success
                        self.check_success_notification()
                        
                        # Verify region in table if configured
                        region_config = self.config.get('systemCreateRegion', {})
                        if region_config.get('validation', {}).get('checkTableEntry', True):
                            self.verify_region_in_table()
                        
                        # Take final screenshot
                        if self.config.get('screenshots', {}).get('enabled', True):
                            self.take_screenshot("createregion_complete")
                        
                        print(f"Region '{self.region_name}' creation completed!")
                    else:
                        print("Could not submit region creation")
                else:
                    print("Could not fill region form")
            else:
                print("Could not open create region dialog")
            
            print("\nTest completed!")
            
            # Keep browser open briefly to observe results
            self.page.wait_for_timeout(2000)
            
        except Exception as e:
            print(f"\nError during test: {str(e)}")
            
            # Take error screenshot
            if self.page and self.config.get('screenshots', {}).get('enabled', True):
                self.take_screenshot("createregion_error")
            
            raise
        
        finally:
            # Cleanup
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            print("Browser closed.")


def main():
    """Entry point"""
    try:
        test = CreateRegionTest()
        with sync_playwright() as playwright:
            test.run(playwright)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()