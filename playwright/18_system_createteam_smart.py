#!/usr/bin/env python3
"""
System Create Team Test - Smart Version
Tests the team creation functionality in Rediacc console
Uses config.json for all settings and credentials
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class TeamCreationTest:
    """Smart team creation test with configuration support"""
    
    def __init__(self, config_path="config.json"):
        """Initialize test with configuration"""
        self.config = self.load_config(config_path)
        self.browser = None
        self.context = None
        self.page = None
        self.test_team = None
        
    def load_config(self, config_path):
        """Load configuration from JSON file"""
        config_file = Path(__file__).parent / config_path
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Add systemCreateTeam configuration if not exists
        if 'systemCreateTeam' not in config:
            config['systemCreateTeam'] = {
                "ui": {
                    "systemNavTestId": "main-nav-system",
                    "teamsTabTestId": "system-tab-teams",
                    "createTeamButtonTestId": "system-create-team-button",
                    "teamNameInputTestId": "resource-modal-field-teamName-input",
                    "sshKeyGenerateButtonTestId": "vault-editor-generate-SSH_PRIVATE_KEY",
                    "generateButtonTestId": "vault-editor-generate-button",
                    "applyGeneratedButtonTestId": "vault-editor-apply-generated",
                    "submitButtonTestId": "resource-modal-ok-button",
                    "cancelButtonTestId": "resource-modal-cancel-button",
                    "teamsTableSelector": "table.ant-table",
                    "modalSelector": ".ant-modal",
                    "keyTypeSelector": "input[value='RSA']",
                    "keySizeSelector": "input[value='4096']"
                },
                "testData": {
                    "teamNamePrefix": "TestTeam",
                    "generateUnique": True,
                    "sshKeyType": "RSA",
                    "sshKeySize": "4096"
                },
                "validation": {
                    "successIndicators": [
                        "Team created successfully",
                        "Team '.*' created successfully",
                        "Successfully created team"
                    ],
                    "errorMessages": [
                        "Team already exists",
                        "Team name is required",
                        "SSH key generation failed"
                    ],
                    "notificationSelectors": [
                        ".ant-message",
                        ".ant-notification",
                        "[role='alert']"
                    ]
                },
                "timeouts": {
                    "navigation": 10000,
                    "element": 5000,
                    "modalOpen": 3000,
                    "sshKeyGeneration": 5000,
                    "creation": 10000,
                    "validation": 5000
                }
            }
        
        return config
    
    def generate_test_team(self):
        """Generate unique test team name"""
        test_config = self.config['systemCreateTeam']['testData']
        
        if test_config.get('generateUnique', True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            team_name = f"{test_config['teamNamePrefix']}_{timestamp}"
        else:
            team_name = test_config['teamNamePrefix']
        
        self.test_team = {
            'name': team_name,
            'sshKeyType': test_config.get('sshKeyType', 'RSA'),
            'sshKeySize': test_config.get('sshKeySize', '4096')
        }
        
        return self.test_team
    
    def setup_browser(self, playwright: Playwright):
        """Setup browser with configuration settings"""
        browser_config = self.config.get('browser', {})
        
        self.browser = playwright.chromium.launch(
            headless=browser_config.get('headless', False),
            slow_mo=browser_config.get('slowMo', 0)
        )
        
        viewport = browser_config.get('viewport', {'width': 1280, 'height': 720})
        self.context = self.browser.new_context(viewport=viewport)
        self.page = self.context.new_page()
        
        # Set default timeout
        default_timeout = self.config.get('timeouts', {}).get('pageLoad', 30000)
        self.page.set_default_timeout(default_timeout)
        
        print(f"Browser setup complete (headless: {browser_config.get('headless', False)})")
    
    def login(self):
        """Login to the application using config credentials"""
        print("\n1. Navigating to login page...")
        
        base_url = self.config.get('baseUrl', 'http://localhost:7322')
        self.page.goto(f"{base_url}/console")
        
        # Wait for login form
        login_config = self.config.get('login', {})
        credentials = login_config.get('credentials', {})
        timeouts = login_config.get('timeouts', {})
        
        print("2. Waiting for login form...")
        
        # Smart wait for email input - try multiple selectors
        email_selectors = [
            f'[data-testid="login-email-input"]',
            'input[type="email"]',
            'input[placeholder*="email" i]'
        ]
        
        email_input = None
        for selector in email_selectors:
            try:
                email_input = self.page.locator(selector).first
                if email_input.is_visible(timeout=1000):
                    break
            except:
                continue
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        # Fill credentials
        print(f"3. Logging in as {credentials.get('email')}...")
        email_input.fill(credentials.get('email', 'admin@rediacc.io'))
        
        # Password input
        password_selectors = [
            f'[data-testid="login-password-input"]',
            'input[type="password"]'
        ]
        
        password_input = None
        for selector in password_selectors:
            try:
                password_input = self.page.locator(selector).first
                if password_input.is_visible(timeout=1000):
                    break
            except:
                continue
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        password_input.fill(credentials.get('password', 'admin'))
        
        # Submit
        submit_selectors = [
            f'[data-testid="login-submit-button"]',
            'button[type="submit"]',
            'button:has-text("Sign In")'
        ]
        
        submit_button = None
        for selector in submit_selectors:
            try:
                submit_button = self.page.locator(selector).first
                if submit_button.is_visible(timeout=1000):
                    break
            except:
                continue
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        submit_button.click()
        
        # Wait for dashboard
        print("4. Waiting for dashboard...")
        dashboard_url = self.config.get('validation', {}).get('dashboardUrl', '**/console/dashboard')
        self.page.wait_for_url(dashboard_url, timeout=timeouts.get('navigation', 10000))
        print("   ✓ Login successful!")
    
    def navigate_to_teams(self):
        """Navigate to System page and Teams tab"""
        print("\n5. Navigating to System page...")
        
        ui_config = self.config['systemCreateTeam']['ui']
        timeouts = self.config['systemCreateTeam']['timeouts']
        
        # Click System nav
        system_nav = self.page.locator(f'[data-testid="{ui_config["systemNavTestId"]}"]')
        expect(system_nav).to_be_visible(timeout=timeouts.get('element', 5000))
        system_nav.click()
        
        # Wait for page load
        self.page.wait_for_load_state("networkidle")
        print("   ✓ On System page")
        
        # Click Teams tab
        print("6. Navigating to Teams tab...")
        teams_tab = self.page.locator(f'[data-testid="{ui_config["teamsTabTestId"]}"]')
        expect(teams_tab).to_be_visible(timeout=timeouts.get('element', 5000))
        teams_tab.click()
        
        # Wait for tab content to load
        self.page.wait_for_load_state("networkidle")
        print("   ✓ On Teams tab")
    
    def create_team(self):
        """Create a new team"""
        print("\n7. Creating new team...")
        
        ui_config = self.config['systemCreateTeam']['ui']
        timeouts = self.config['systemCreateTeam']['timeouts']
        
        # Generate test team
        team = self.generate_test_team()
        print(f"   Test team: {team['name']}")
        
        # Click create team button
        create_button = self.page.locator(f'[data-testid="{ui_config["createTeamButtonTestId"]}"]')
        expect(create_button).to_be_visible(timeout=timeouts.get('element', 5000))
        create_button.click()
        print("   ✓ Create team modal opened")
        
        # Wait for modal
        modal = self.page.locator(ui_config['modalSelector'])
        expect(modal).to_be_visible(timeout=timeouts.get('modalOpen', 3000))
        
        # Fill team name
        team_name_input = self.page.locator(f'[data-testid="{ui_config["teamNameInputTestId"]}"]')
        expect(team_name_input).to_be_visible(timeout=timeouts.get('element', 5000))
        team_name_input.fill(team['name'])
        print(f"   ✓ Team name filled: {team['name']}")
        
        # Generate SSH key
        print("8. Generating SSH key...")
        self.generate_ssh_key()
        
        # Submit
        submit_button = self.page.locator(f'[data-testid="{ui_config["submitButtonTestId"]}"]')
        expect(submit_button).to_be_visible(timeout=timeouts.get('element', 5000))
        submit_button.click()
        print("   ✓ Form submitted")
        
        return team
    
    def generate_ssh_key(self):
        """Generate SSH key for the team"""
        ui_config = self.config['systemCreateTeam']['ui']
        timeouts = self.config['systemCreateTeam']['timeouts']
        
        try:
            # Click generate SSH key button
            generate_ssh_button = self.page.locator(f'[data-testid="{ui_config["sshKeyGenerateButtonTestId"]}"]')
            expect(generate_ssh_button).to_be_visible(timeout=timeouts.get('element', 5000))
            generate_ssh_button.click()
            print("   ✓ SSH key generation dialog opened")
            
            # Wait for generation dialog
            self.page.wait_for_timeout(500)
            
            # Select key type (RSA) - click the label or the radio itself
            try:
                key_type_label = self.page.locator('label:has-text("RSA")')
                if key_type_label.is_visible():
                    key_type_label.click()
                    print("   ✓ Selected RSA key type")
            except:
                # Fallback to radio button
                key_type_radio = self.page.locator('input[value="RSA"]')
                if key_type_radio.is_visible():
                    key_type_radio.click()
                    print("   ✓ Selected RSA key type")
            
            # Select key size (4096) - click the label or the radio itself
            try:
                key_size_label = self.page.locator('label:has-text("4096")')
                if key_size_label.is_visible():
                    key_size_label.click()
                    print("   ✓ Selected 4096 bit key size")
            except:
                # Fallback to radio button
                key_size_radio = self.page.locator('input[value="4096"]')
                if key_size_radio.is_visible():
                    key_size_radio.click()
                    print("   ✓ Selected 4096 bit key size")
            
            # Click generate button
            generate_button = self.page.locator(f'[data-testid="{ui_config["generateButtonTestId"]}"]')
            if generate_button.is_visible():
                generate_button.click()
                print("   ✓ Generating SSH key...")
                
                # Wait for key generation
                self.page.wait_for_timeout(timeouts.get('sshKeyGeneration', 5000))
                
                # Apply generated key
                apply_button = self.page.locator(f'[data-testid="{ui_config["applyGeneratedButtonTestId"]}"]')
                if apply_button.is_visible():
                    apply_button.click()
                    print("   ✓ SSH key generated and applied")
                    return True
        except Exception as e:
            print(f"   ⚠ SSH key generation failed: {str(e)}")
            # Continue without SSH key - it might be optional
            return False
    
    def validate_creation(self, team):
        """Validate team creation success"""
        print("\n9. Validating team creation...")
        
        ui_config = self.config['systemCreateTeam']['ui']
        validation_config = self.config['systemCreateTeam']['validation']
        timeouts = self.config['systemCreateTeam']['timeouts']
        
        success = False
        
        # Method 1: Check if modal closed
        try:
            modal = self.page.locator(ui_config['modalSelector'])
            expect(modal).not_to_be_visible(timeout=timeouts.get('creation', 10000))
            print("   ✓ Modal closed successfully")
            success = True
        except:
            print("   ⚠ Modal still visible")
        
        # Method 2: Check for success notification
        for selector in validation_config.get('notificationSelectors', []):
            try:
                notification = self.page.locator(selector)
                if notification.is_visible():
                    text = notification.text_content()
                    print(f"   ✓ Notification found: {text}")
                    for indicator in validation_config.get('successIndicators', []):
                        if indicator.replace('.*', '') in text:
                            success = True
                            break
            except:
                continue
        
        # Method 3: Check if team appears in table
        try:
            table = self.page.locator(ui_config['teamsTableSelector'])
            expect(table).to_be_visible(timeout=timeouts.get('validation', 5000))
            
            # Look for the new team in the table
            team_row = self.page.locator(f'text="{team["name"]}"')
            if team_row.is_visible():
                print(f"   ✓ Team {team['name']} found in table")
                success = True
        except:
            print("   ⚠ Could not verify team in table")
        
        return success
    
    def take_screenshot(self, name="screenshot"):
        """Take screenshot for documentation"""
        screenshots_config = self.config.get('screenshots', {})
        if not screenshots_config.get('enabled', True):
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_dir = Path(__file__).parent / screenshots_config.get('path', './artifacts/screenshots')
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        screenshot_path = screenshot_dir / f"{name}_{timestamp}.png"
        self.page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"   📸 Screenshot saved: {screenshot_path}")
    
    def cleanup(self):
        """Cleanup browser resources"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        print("\n✓ Browser closed")
    
    def run(self, playwright: Playwright):
        """Main test execution"""
        try:
            print("=" * 60)
            print("System Create Team Test - Smart Version")
            print("=" * 60)
            
            # Setup
            self.setup_browser(playwright)
            
            # Login
            self.login()
            
            # Navigate to Teams
            self.navigate_to_teams()
            
            # Take screenshot of Teams page
            self.take_screenshot("teams_page")
            
            # Create team
            team = self.create_team()
            
            # Wait for API processing
            self.page.wait_for_timeout(2000)
            
            # Validate
            success = self.validate_creation(team)
            
            # Take final screenshot
            self.take_screenshot("team_created")
            
            # Report result
            print("\n" + "=" * 60)
            if success:
                print("✅ TEST PASSED: Team created successfully!")
                print(f"   Team Name: {team['name']}")
            else:
                print("❌ TEST FAILED: Team creation could not be verified")
            print("=" * 60)
            
            # Keep browser open briefly to see results
            self.page.wait_for_timeout(2000)
            
            return 0 if success else 1
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            
            # Take error screenshot
            try:
                self.take_screenshot("error")
            except:
                pass
            
            raise
        
        finally:
            self.cleanup()


def main():
    """Entry point"""
    try:
        test = TeamCreationTest()
        
        with sync_playwright() as playwright:
            exit_code = test.run(playwright)
            sys.exit(exit_code)
            
    except KeyboardInterrupt:
        print("\n⚠ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()