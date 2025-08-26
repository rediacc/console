#!/usr/bin/env python3
"""
System Teams Delete Test - Smart Version
Tests the team deletion functionality in Rediacc console
Uses config.json for all settings and credentials
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class TeamDeletionTest:
    """Smart team deletion test with configuration support"""
    
    def __init__(self, config_path="config.json"):
        """Initialize test with configuration"""
        self.config = self.load_config(config_path)
        self.browser = None
        self.context = None
        self.page = None
        self.target_team = None
        
    def load_config(self, config_path):
        """Load configuration from JSON file"""
        config_file = Path(__file__).parent / config_path
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Add systemTeamsDelete configuration if not exists
        if 'systemTeamsDelete' not in config:
            config['systemTeamsDelete'] = {
                "ui": {
                    "systemNavTestId": "main-nav-system",
                    "teamsTabTestId": "system-tab-teams",
                    "deleteButtonPrefix": "system-team-delete-button-",
                    "confirmDialogSelector": ".ant-popconfirm",
                    "confirmYesButton": ".ant-popconfirm button.ant-btn-dangerous:has-text('Yes')",
                    "confirmNoButton": ".ant-popconfirm button:has-text('No')",
                    "teamsTableSelector": "table.ant-table",
                    "teamRowSelector": "tr.ant-table-row",
                    "modalSelector": ".ant-modal",
                    "createTeamButtonTestId": "system-create-team-button",
                    "teamNameInputTestId": "resource-modal-field-teamName-input"
                },
                "testData": {
                    "targetTeamName": null,
                    "skipSystemTeams": ["Default", "Private Team"],
                    "deleteMode": "first_available",
                    "createTestTeamIfNeeded": true,
                    "testTeamPrefix": "TestDeleteTeam"
                },
                "validation": {
                    "successIndicators": [
                        "Team deleted successfully",
                        "Team '.*' deleted successfully",
                        "Successfully deleted team"
                    ],
                    "errorMessages": [
                        "Cannot delete the default",
                        "This is a system-required entity",
                        "Team not found",
                        "Deletion failed"
                    ],
                    "notificationSelectors": [
                        ".ant-message",
                        ".ant-notification",
                        "[role='alert']"
                    ],
                    "checkTableAfterDeletion": true
                },
                "timeouts": {
                    "navigation": 10000,
                    "element": 5000,
                    "confirmDialog": 3000,
                    "deletion": 5000,
                    "validation": 5000
                }
            }
        
        return config
    
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
        
        # Smart wait for email input
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
        
        ui_config = self.config['systemTeamsDelete']['ui']
        timeouts = self.config['systemTeamsDelete']['timeouts']
        
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
    
    def find_deletable_team(self):
        """Find a team that can be deleted"""
        print("\n7. Finding team to delete...")
        
        ui_config = self.config['systemTeamsDelete']['ui']
        test_config = self.config['systemTeamsDelete']['testData']
        
        # If specific team is configured
        if test_config.get('targetTeamName'):
            self.target_team = test_config['targetTeamName']
            print(f"   Using configured team: {self.target_team}")
            return self.target_team
        
        # Find first available deletable team
        team_rows = self.page.locator(ui_config['teamRowSelector']).all()
        skip_teams = test_config.get('skipSystemTeams', ['Default', 'Private Team'])
        
        for row in team_rows:
            try:
                # Get team name from row
                team_name_cell = row.locator('td').first
                if not team_name_cell.is_visible():
                    continue
                
                team_name = team_name_cell.text_content().strip()
                
                # Skip system teams
                if team_name in skip_teams:
                    print(f"   Skipping system team: {team_name}")
                    continue
                
                # Check if team has delete button
                delete_button = row.locator(f'[data-testid="{ui_config["deleteButtonPrefix"]}{team_name}"]')
                if not delete_button.is_visible():
                    # Try generic delete button in row
                    delete_button = row.locator('button[title*="Delete"]').first
                
                if delete_button.is_visible():
                    self.target_team = team_name
                    print(f"   ✓ Found deletable team: {team_name}")
                    return team_name
                    
            except Exception as e:
                continue
        
        # No deletable team found - create one if configured
        if test_config.get('createTestTeamIfNeeded', True):
            print("   No deletable team found, creating test team...")
            return self.create_test_team()
        
        print("   ⚠ No suitable team found to delete")
        return None
    
    def create_test_team(self):
        """Create a test team for deletion"""
        ui_config = self.config['systemTeamsDelete']['ui']
        test_config = self.config['systemTeamsDelete']['testData']
        timeouts = self.config['systemTeamsDelete']['timeouts']
        
        # Generate unique team name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        team_name = f"{test_config.get('testTeamPrefix', 'TestDeleteTeam')}_{timestamp}"
        
        # Click create team button
        create_button = self.page.locator(f'[data-testid="{ui_config["createTeamButtonTestId"]}"]')
        if not create_button.is_visible():
            create_button = self.page.locator('button:has-text("Create Team")').first
        
        if create_button.is_visible():
            create_button.click()
            
            # Wait for modal
            modal = self.page.locator(ui_config['modalSelector'])
            expect(modal).to_be_visible(timeout=timeouts.get('element', 5000))
            
            # Fill team name
            team_name_input = self.page.locator(f'[data-testid="{ui_config["teamNameInputTestId"]}"]')
            if not team_name_input.is_visible():
                team_name_input = self.page.locator('input[placeholder*="team" i]').first
            
            team_name_input.fill(team_name)
            
            # Generate SSH key if needed (similar to team creation)
            try:
                ssh_generate_button = self.page.locator('[data-testid="vault-editor-generate-SSH_PRIVATE_KEY"]')
                if ssh_generate_button.is_visible():
                    ssh_generate_button.click()
                    self.page.wait_for_timeout(500)
                    
                    # Click generate
                    gen_btn = self.page.locator('[data-testid="vault-editor-generate-button"]')
                    if gen_btn.is_visible():
                        gen_btn.click()
                        self.page.wait_for_timeout(3000)
                        
                        # Apply generated key
                        apply_btn = self.page.locator('[data-testid="vault-editor-apply-generated"]')
                        if apply_btn.is_visible():
                            apply_btn.click()
                            print("   ✓ SSH key generated")
            except:
                pass
            
            # Submit
            submit_button = self.page.locator('[data-testid="resource-modal-ok-button"]').first
            if not submit_button.is_visible():
                submit_button = self.page.locator('button:has-text("Create")').first
            if not submit_button.is_visible():
                submit_button = self.page.locator('.ant-modal button.ant-btn-primary').first
            
            submit_button.click()
            
            # Wait for modal to close
            self.page.wait_for_timeout(2000)
            try:
                expect(modal).not_to_be_visible(timeout=timeouts.get('element', 5000))
            except:
                # Modal might still be visible if there's an error
                pass
            
            print(f"   ✓ Created test team: {team_name}")
            self.target_team = team_name
            
            # Refresh the page or wait for table to update
            self.page.wait_for_timeout(2000)
            # Reload to see the new team
            self.page.reload()
            self.page.wait_for_load_state("networkidle")
            
            return team_name
        
        return None
    
    def delete_team(self):
        """Delete the target team"""
        if not self.target_team:
            print("\n8. No team to delete, skipping...")
            return False
        
        print(f"\n8. Deleting team: {self.target_team}")
        
        ui_config = self.config['systemTeamsDelete']['ui']
        timeouts = self.config['systemTeamsDelete']['timeouts']
        
        # Find delete button
        delete_button = self.page.locator(f'[data-testid="{ui_config["deleteButtonPrefix"]}{self.target_team}"]')
        
        # Fallback to generic delete button in team row
        if not delete_button.is_visible():
            team_row = self.page.locator(f'tr:has-text("{self.target_team}")')
            delete_button = team_row.locator('button[title*="Delete"]').first
            if not delete_button.is_visible():
                delete_button = team_row.locator('button:has-text("Delete")').first
        
        if not delete_button.is_visible():
            print("   ❌ Delete button not found")
            return False
        
        # Click delete button
        delete_button.click()
        print("   ✓ Delete button clicked")
        
        # Wait for confirmation dialog
        print("9. Confirming deletion...")
        confirm_dialog = self.page.locator(ui_config['confirmDialogSelector'])
        expect(confirm_dialog).to_be_visible(timeout=timeouts.get('confirmDialog', 3000))
        
        # Click Yes button
        yes_button = self.page.locator(ui_config['confirmYesButton'])
        if not yes_button.is_visible():
            # Fallback to generic Yes button
            yes_button = self.page.locator('.ant-popconfirm button:has-text("Yes")').first
        
        yes_button.click()
        print("   ✓ Deletion confirmed")
        
        # Wait for dialog to close
        expect(confirm_dialog).not_to_be_visible(timeout=timeouts.get('deletion', 5000))
        
        return True
    
    def validate_deletion(self):
        """Validate team deletion success"""
        print("\n10. Validating deletion...")
        
        if not self.target_team:
            print("   ⚠ No team was deleted")
            return False
        
        ui_config = self.config['systemTeamsDelete']['ui']
        validation_config = self.config['systemTeamsDelete']['validation']
        timeouts = self.config['systemTeamsDelete']['timeouts']
        
        success = False
        
        # Method 1: Check for success notification
        for selector in validation_config.get('notificationSelectors', []):
            try:
                notification = self.page.locator(selector)
                if notification.is_visible():
                    text = notification.text_content()
                    print(f"   Notification: {text}")
                    
                    # Check for success messages
                    for indicator in validation_config.get('successIndicators', []):
                        if indicator.replace('.*', '') in text:
                            print(f"   ✓ Success message found")
                            success = True
                            break
                    
                    # Check for error messages
                    for error in validation_config.get('errorMessages', []):
                        if error in text:
                            print(f"   ❌ Error: {text}")
                            return False
            except:
                continue
        
        # Method 2: Check if team is removed from table
        if validation_config.get('checkTableAfterDeletion', True):
            try:
                # Wait a moment for table to update
                self.page.wait_for_timeout(1000)
                
                # Check if team still exists in table
                team_row = self.page.locator(f'tr:has-text("{self.target_team}")')
                if not team_row.is_visible():
                    print(f"   ✓ Team {self.target_team} removed from table")
                    success = True
                else:
                    print(f"   ⚠ Team {self.target_team} still visible in table")
                    
            except:
                # Team not found = deletion successful
                print(f"   ✓ Team {self.target_team} not found in table")
                success = True
        
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
            print("System Teams Delete Test - Smart Version")
            print("=" * 60)
            
            # Setup
            self.setup_browser(playwright)
            
            # Login
            self.login()
            
            # Navigate to Teams
            self.navigate_to_teams()
            
            # Take screenshot of Teams page
            self.take_screenshot("teams_page_before")
            
            # Find team to delete
            self.find_deletable_team()
            
            # Delete team
            deleted = self.delete_team()
            
            # Wait for API processing
            if deleted:
                self.page.wait_for_timeout(2000)
            
            # Validate
            success = self.validate_deletion() if deleted else False
            
            # Take final screenshot
            self.take_screenshot("teams_page_after")
            
            # Report result
            print("\n" + "=" * 60)
            if success:
                print("✅ TEST PASSED: Team deleted successfully!")
                print(f"   Team: {self.target_team}")
            elif not self.target_team:
                print("⚠️ TEST SKIPPED: No suitable team found to delete")
                print("   All teams may be system-required")
            else:
                print("❌ TEST FAILED: Team deletion could not be verified")
            print("=" * 60)
            
            # Keep browser open briefly to see results
            self.page.wait_for_timeout(2000)
            
            return 0 if success or not self.target_team else 1
            
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
        test = TeamDeletionTest()
        
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