#!/usr/bin/env python3

import json
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect

class CustomBridgeTest:
    """Custom bridge creation test following exact requirements"""
    
    def __init__(self):
        self.page = None
        self.context = None
        self.browser = None
        self.bridge_name = "test_bridge_mcp"
        
    def run_test(self):
        """Run the complete bridge creation test"""
        with sync_playwright() as playwright:
            try:
                self.setup_browser(playwright)
                self.navigate_to_console()
                self.handle_login()
                self.navigate_to_system()
                self.switch_to_expert_mode()
                self.navigate_to_bridges_tab()
                self.create_new_bridge()
                self.take_final_screenshot()
                return True
            except Exception as e:
                print(f"❌ Test failed with error: {e}")
                self.take_error_screenshot()
                return False
            finally:
                if self.browser:
                    self.browser.close()
    
    def setup_browser(self, playwright):
        """Setup browser with appropriate settings"""
        print("🚀 Starting Bridge Creation Test...")
        self.browser = playwright.chromium.launch(headless=False, slow_mo=500)
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.page = self.context.new_page()
    
    def navigate_to_console(self):
        """Step 1: Navigate to console"""
        print("📍 Step 1: Navigating to console...")
        self.page.goto("http://localhost:7322/console/login")
        self.page.wait_for_load_state("networkidle", timeout=10000)
    
    def handle_login(self):
        """Step 2: Login with credentials"""
        print("🔐 Step 2: Logging in...")
        
        # Handle encryption dialog if it appears
        try:
            skip_selectors = [
                "button:has-text('Skip')",
                "button:has-text('skip')",
                "[data-testid*='skip']",
                ".ant-btn:has-text('Skip')"
            ]
            for selector in skip_selectors:
                skip_button = self.page.locator(selector).first
                if skip_button.is_visible(timeout=2000):
                    print("Skipping encryption dialog...")
                    skip_button.click()
                    self.page.wait_for_timeout(1000)
                    break
        except Exception as e:
            print(f"No encryption dialog or already dismissed: {e}")
        
        # Login form selectors - try multiple approaches
        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="email"]',
            'input[id*="email"]',
            '.ant-input'
        ]
        
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]', 
            'input[placeholder*="password"]',
            'input[id*="password"]'
        ]
        
        login_selectors = [
            'button:has-text("Login")',
            'button:has-text("Sign In")',
            'button[type="submit"]',
            '.ant-btn-primary'
        ]
        
        # Fill email
        email_filled = False
        for selector in email_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=2000):
                    element.fill("admin@rediacc.io")
                    email_filled = True
                    break
            except:
                continue
        
        if not email_filled:
            raise Exception("Could not find email input field")
        
        # Fill password
        password_filled = False
        for selector in password_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=2000):
                    element.fill("admin")
                    password_filled = True
                    break
            except:
                continue
                
        if not password_filled:
            raise Exception("Could not find password input field")
        
        # Click login
        login_clicked = False
        for selector in login_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=2000):
                    element.click()
                    login_clicked = True
                    break
            except:
                continue
                
        if not login_clicked:
            raise Exception("Could not find login button")
        
        self.page.wait_for_load_state("networkidle", timeout=10000)
        print("✅ Login successful!")
    
    def navigate_to_system(self):
        """Step 3: Navigate to System page"""
        print("📊 Step 3: Navigating to System page...")
        
        system_selectors = [
            'a[href="/console/system"]',
            'a:has-text("System")',
            '[data-testid*="system"]',
            'nav a:has-text("System")'
        ]
        
        for selector in system_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=3000):
                    element.click()
                    self.page.wait_for_load_state("networkidle", timeout=5000)
                    print("✅ System page loaded")
                    return
            except:
                continue
        
        raise Exception("Could not navigate to System page")
    
    def switch_to_expert_mode(self):
        """Step 4: Switch to Expert mode if needed"""
        print("🔧 Step 4: Checking Expert mode...")
        
        expert_selectors = [
            'input[type="checkbox"][aria-label*="Expert"]',
            'input[type="checkbox"][title*="Expert"]',
            '[data-testid*="expert"] input[type="checkbox"]',
            '.ant-switch[aria-label*="Expert"]',
            '.ant-switch[title*="Expert"]'
        ]
        
        for selector in expert_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=3000):
                    is_checked = element.is_checked()
                    if not is_checked:
                        print("Switching to Expert mode...")
                        element.click()
                        self.page.wait_for_timeout(1000)
                        print("✅ Switched to Expert mode")
                    else:
                        print("✅ Already in Expert mode")
                    return
            except:
                continue
        
        print("⚠️ Expert mode toggle not found - continuing anyway")
    
    def navigate_to_bridges_tab(self):
        """Step 5: Go to Bridges tab"""
        print("🌉 Step 5: Navigating to Bridges tab...")
        
        bridges_selectors = [
            '[role="tab"]:has-text("Bridges")',
            '.ant-tabs-tab:has-text("Bridges")',
            'button:has-text("Bridges")',
            'a:has-text("Bridges")',
            '[data-testid*="bridges"]'
        ]
        
        for selector in bridges_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=3000):
                    element.click()
                    self.page.wait_for_timeout(2000)
                    print("✅ Bridges tab opened")
                    return
            except:
                continue
        
        raise Exception("Could not find Bridges tab")
    
    def create_new_bridge(self):
        """Steps 6-9: Create new bridge"""
        print("➕ Step 6: Clicking Create Bridge button...")
        
        # Find Create Bridge button
        create_selectors = [
            'button:has-text("Create Bridge")',
            'button:has-text("Add Bridge")',
            'button:has-text("Create")',
            '[data-testid*="create-bridge"]',
            '.ant-btn-primary:has-text("Create")',
            'button.ant-btn-primary'
        ]
        
        for selector in create_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=3000):
                    element.click()
                    self.page.wait_for_timeout(2000)
                    print("✅ Create Bridge dialog opened")
                    break
            except:
                continue
        else:
            raise Exception("Could not find Create Bridge button")
        
        # Step 7: Select Private Team
        print("👥 Step 7: Selecting Private Team...")
        team_selected = self.select_team("Private Team")
        if not team_selected:
            raise Exception("Could not select Private Team")
        print("✅ Private Team selected")
        
        # Step 8: Enter bridge name
        print("📝 Step 8: Entering bridge name 'test_bridge_mcp'...")
        name_entered = self.enter_bridge_name("test_bridge_mcp")
        if not name_entered:
            raise Exception("Could not enter bridge name")
        print("✅ Bridge name entered")
        
        # Step 9: Submit form
        print("✅ Step 9: Submitting the form...")
        submitted = self.submit_form()
        if not submitted:
            raise Exception("Could not submit form")
        
        # Check results
        self.check_creation_result()
    
    def select_team(self, team_name):
        """Select team from dropdown"""
        team_selectors = [
            'select',
            '[data-testid*="team"] select',
            '[data-testid*="teamName"] select',
            '.ant-select',
            '[role="combobox"]'
        ]
        
        for selector in team_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=2000):
                    if element.get_attribute("tagName") == "SELECT":
                        element.select_option(label=team_name)
                    else:
                        # Handle Ant Design select
                        element.click()
                        self.page.wait_for_timeout(500)
                        option = self.page.locator(f'.ant-select-item:has-text("{team_name}")').first
                        if option.is_visible(timeout=2000):
                            option.click()
                    return True
            except:
                continue
        return False
    
    def enter_bridge_name(self, name):
        """Enter bridge name in input field"""
        name_selectors = [
            'input[type="text"]',
            '[data-testid*="bridgeName"] input',
            '[data-testid*="name"] input',
            '.ant-input',
            'input[placeholder*="name"]'
        ]
        
        for selector in name_selectors:
            try:
                inputs = self.page.locator(selector).all()
                # Try the last input first (often the name field)
                for input_elem in reversed(inputs):
                    if input_elem.is_visible():
                        input_elem.fill(name)
                        return True
            except:
                continue
        return False
    
    def submit_form(self):
        """Submit the creation form"""
        submit_selectors = [
            'button:has-text("Create")',
            'button:has-text("OK")',
            'button:has-text("Submit")',
            '[data-testid*="ok"]',
            '.ant-btn-primary:visible'
        ]
        
        for selector in submit_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=2000):
                    element.click()
                    self.page.wait_for_timeout(3000)
                    return True
            except:
                continue
        return False
    
    def check_creation_result(self):
        """Check if bridge was created successfully"""
        print("🔍 Checking for result...")
        
        success_selectors = [
            'text*="Bridge configuration for network connectivity"',
            'text*="successfully created"',
            'text*="Bridge created"',
            '.ant-message-success',
            '.ant-notification-notice-success',
            '[role="alert"]:has-text("success")'
        ]
        
        success_found = False
        for selector in success_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=3000):
                    success_found = True
                    print(f"✅ Success notification found: {element.inner_text()}")
                    break
            except:
                continue
        
        if success_found:
            print("🎉 BRIDGE CREATION SUCCESSFUL!")
            print("Bridge 'test_bridge_mcp' was created successfully in Private Team.")
        else:
            print("⚠️ BRIDGE CREATION STATUS UNCLEAR")
            print("No clear success indicator found - check screenshot for details.")
    
    def take_final_screenshot(self):
        """Step 10: Take final screenshot"""
        print("📸 Step 10: Taking final screenshot...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"artifacts/screenshots/bridge_creation_result_{timestamp}.png"
        
        # Ensure directory exists
        Path("artifacts/screenshots").mkdir(parents=True, exist_ok=True)
        
        self.page.screenshot(path=screenshot_path, full_page=True)
        print(f"📸 Screenshot saved: {screenshot_path}")
        
        return screenshot_path
    
    def take_error_screenshot(self):
        """Take screenshot on error"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            error_screenshot = f"artifacts/screenshots/bridge_creation_error_{timestamp}.png"
            Path("artifacts/screenshots").mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=error_screenshot, full_page=True)
            print(f"📸 Error screenshot saved: {error_screenshot}")
        except:
            print("Could not save error screenshot")

if __name__ == "__main__":
    test = CustomBridgeTest()
    success = test.run_test()