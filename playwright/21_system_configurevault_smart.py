#!/usr/bin/env python3
"""
System Configure Vault Test - Smart Version
Tests the vault configuration functionality in Rediacc console
Uses config.json for all settings and credentials
"""

import json
import time
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect


class VaultConfigurationTest:
    """Smart vault configuration test with configuration support"""
    
    def __init__(self, config_path="config.json"):
        """Initialize test with configuration"""
        self.config = self.load_config(config_path)
        self.browser = None
        self.context = None
        self.page = None
        self.vault_type = None
        
    def load_config(self, config_path):
        """Load configuration from JSON file"""
        config_file = Path(__file__).parent / config_path
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Add systemVaultConfiguration if not exists
        if 'systemVaultConfiguration' not in config:
            config['systemVaultConfiguration'] = {
                "ui": {
                    "systemNavTestId": "main-nav-system",
                    "companyVaultButtonTestId": "system-company-vault-button",
                    "userVaultButtonPrefix": "system-user-vault-button",
                    "teamsTabTestId": "system-tab-teams",
                    "teamVaultButtonPrefix": "system-team-vault-button",
                    "sshGenerateButtonTestId": "vault-editor-generate-SSH_PRIVATE_KEY",
                    "generateButtonTestId": "vault-editor-generate-button",
                    "applyGeneratedButtonTestId": "vault-editor-apply-generated",
                    "saveButtonTestId": "vault-modal-save-button",
                    "cancelButtonTestId": "vault-modal-cancel-button",
                    "modalSelector": ".ant-modal",
                    "vaultFieldPrefix": "vault-editor-field-",
                    "keyTypeSelector": "input[value='RSA']",
                    "keySizeSelector": "input[value='4096']",
                    "universalUserIdField": "vault-editor-field-UNIVERSAL_USER_ID",
                    "universalUserNameField": "vault-editor-field-UNIVERSAL_USER_NAME"
                },
                "testData": {
                    "vaultType": "company",
                    "targetUser": null,
                    "targetTeam": null,
                    "sshKeyType": "RSA",
                    "sshKeySize": "4096",
                    "universalUserId": "universal_user_001",
                    "universalUserName": "Universal User",
                    "dockerConfig": null,
                    "plugins": null
                },
                "validation": {
                    "successIndicators": [
                        "Vault configuration saved successfully",
                        "Vault updated successfully",
                        "Configuration saved"
                    ],
                    "errorMessages": [
                        "Required fields missing",
                        "Invalid configuration",
                        "Save failed"
                    ],
                    "notificationSelectors": [
                        ".ant-message",
                        ".ant-notification",
                        "[role='alert']"
                    ],
                    "checkRequiredFields": true
                },
                "timeouts": {
                    "navigation": 10000,
                    "element": 5000,
                    "modalOpen": 3000,
                    "sshKeyGeneration": 5000,
                    "save": 5000,
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
    
    def navigate_to_system(self):
        """Navigate to System page"""
        print("\n5. Navigating to System page...")
        
        ui_config = self.config['systemVaultConfiguration']['ui']
        timeouts = self.config['systemVaultConfiguration']['timeouts']
        
        # Click System nav
        system_nav = self.page.locator(f'[data-testid="{ui_config["systemNavTestId"]}"]')
        expect(system_nav).to_be_visible(timeout=timeouts.get('element', 5000))
        system_nav.click()
        
        # Wait for page load
        self.page.wait_for_load_state("networkidle")
        print("   ✓ On System page")
    
    def open_vault_configuration(self):
        """Open vault configuration dialog"""
        print("\n6. Opening vault configuration...")
        
        ui_config = self.config['systemVaultConfiguration']['ui']
        test_config = self.config['systemVaultConfiguration']['testData']
        timeouts = self.config['systemVaultConfiguration']['timeouts']
        
        self.vault_type = test_config.get('vaultType', 'company')
        
        if self.vault_type == 'company':
            # Click Company Vault button
            vault_button = self.page.locator(f'[data-testid="{ui_config["companyVaultButtonTestId"]}"]')
            print("   Opening Company vault...")
        elif self.vault_type == 'user':
            # Find specific user vault button
            target_user = test_config.get('targetUser')
            if target_user:
                vault_button = self.page.locator(f'[data-testid="{ui_config["userVaultButtonPrefix"]}-{target_user}"]')
            else:
                # First available user vault
                vault_button = self.page.locator(f'[data-testid^="{ui_config["userVaultButtonPrefix"]}"]').first
            print(f"   Opening User vault{' for ' + target_user if target_user else ''}...")
        elif self.vault_type == 'team':
            # Navigate to Teams tab first
            teams_tab = self.page.locator(f'[data-testid="{ui_config["teamsTabTestId"]}"]')
            if teams_tab.is_visible():
                teams_tab.click()
                self.page.wait_for_load_state("networkidle")
            
            # Find specific team vault button
            target_team = test_config.get('targetTeam')
            if target_team:
                vault_button = self.page.locator(f'[data-testid="{ui_config["teamVaultButtonPrefix"]}-{target_team}"]')
            else:
                # First available team vault
                vault_button = self.page.locator(f'[data-testid^="{ui_config["teamVaultButtonPrefix"]}"]').first
            print(f"   Opening Team vault{' for ' + target_team if target_team else ''}...")
        else:
            raise ValueError(f"Invalid vault type: {self.vault_type}")
        
        # Fallback to generic vault button
        if not vault_button.is_visible():
            vault_button = self.page.locator('button:has-text("Vault")').first
        
        expect(vault_button).to_be_visible(timeout=timeouts.get('element', 5000))
        vault_button.click()
        
        # Wait for modal
        modal = self.page.locator(ui_config['modalSelector'])
        expect(modal).to_be_visible(timeout=timeouts.get('modalOpen', 3000))
        print(f"   ✓ {self.vault_type.capitalize()} vault configuration opened")
    
    def fill_required_fields(self):
        """Fill required vault fields"""
        print("\n7. Filling required fields...")
        
        ui_config = self.config['systemVaultConfiguration']['ui']
        test_config = self.config['systemVaultConfiguration']['testData']
        timeouts = self.config['systemVaultConfiguration']['timeouts']
        
        # Try to fill all visible input fields with data if they're empty
        # This is a more comprehensive approach for vault fields
        
        # Fill Universal User ID
        try:
            user_id_field = self.page.locator(f'[data-testid="{ui_config["universalUserIdField"]}"]')
            if not user_id_field.is_visible():
                # Try alternative selector
                user_id_field = self.page.locator('input[placeholder*="Universal User ID" i]').first
            
            if user_id_field.is_visible():
                current_value = user_id_field.input_value()
                if not current_value:
                    user_id_field.fill(test_config.get('universalUserId', 'universal_user_001'))
                    print(f"   ✓ Universal User ID filled: {test_config.get('universalUserId')}")
        except:
            pass
        
        # Fill Universal User Name
        try:
            user_name_field = self.page.locator(f'[data-testid="{ui_config["universalUserNameField"]}"]')
            if not user_name_field.is_visible():
                # Try alternative selector
                user_name_field = self.page.locator('input[placeholder*="Universal User Name" i]').first
            
            if user_name_field.is_visible():
                current_value = user_name_field.input_value()
                if not current_value:
                    user_name_field.fill(test_config.get('universalUserName', 'Universal User'))
                    print(f"   ✓ Universal User Name filled: {test_config.get('universalUserName')}")
        except:
            pass
        
        # Fill any other empty required fields
        # Look for all text inputs in the modal
        try:
            all_inputs = self.page.locator('.ant-modal input[type="text"], .ant-modal textarea').all()
            for input_field in all_inputs:
                try:
                    # Check if field is visible and empty
                    if input_field.is_visible():
                        current_value = input_field.input_value()
                        placeholder = input_field.get_attribute('placeholder') or ''
                        
                        if not current_value and placeholder:
                            # Generate appropriate value based on placeholder
                            if 'user' in placeholder.lower() and 'id' in placeholder.lower():
                                input_field.fill('universal_user_001')
                                print(f"   ✓ Filled field with placeholder '{placeholder}'")
                            elif 'user' in placeholder.lower() and 'name' in placeholder.lower():
                                input_field.fill('Universal User')
                                print(f"   ✓ Filled field with placeholder '{placeholder}'")
                            elif 'datastore' in placeholder.lower():
                                input_field.fill('/mnt/datastore')
                                print(f"   ✓ Filled datastore path")
                            elif placeholder and not current_value:
                                # Fill with a generic value
                                input_field.fill('default_value')
                                print(f"   ✓ Filled field with placeholder '{placeholder}'")
                except:
                    pass
        except:
            pass
    
    def generate_ssh_key(self):
        """Generate SSH key in vault"""
        print("\n8. Generating SSH key...")
        
        ui_config = self.config['systemVaultConfiguration']['ui']
        test_config = self.config['systemVaultConfiguration']['testData']
        timeouts = self.config['systemVaultConfiguration']['timeouts']
        
        try:
            # Click generate SSH key button
            generate_ssh_button = self.page.locator(f'[data-testid="{ui_config["sshGenerateButtonTestId"]}"]')
            
            # Fallback selector
            if not generate_ssh_button.is_visible():
                generate_ssh_button = self.page.locator('button[title*="Generate SSH"]').first
            
            if not generate_ssh_button.is_visible():
                print("   ⚠ SSH key generation button not found")
                return False
            
            generate_ssh_button.click()
            print("   ✓ SSH key generation dialog opened")
            
            # Wait for generation dialog
            self.page.wait_for_timeout(500)
            
            # Select key type (RSA)
            try:
                key_type_label = self.page.locator('label:has-text("RSA")')
                if key_type_label.is_visible():
                    key_type_label.click()
                    print(f"   ✓ Selected {test_config.get('sshKeyType', 'RSA')} key type")
            except:
                pass
            
            # Select key size (4096)
            try:
                key_size = test_config.get('sshKeySize', '4096')
                key_size_label = self.page.locator(f'label:has-text("{key_size}")')
                if key_size_label.is_visible():
                    key_size_label.click()
                    print(f"   ✓ Selected {key_size} bit key size")
            except:
                pass
            
            # Click generate button
            generate_button = self.page.locator(f'[data-testid="{ui_config["generateButtonTestId"]}"]')
            if not generate_button.is_visible():
                generate_button = self.page.locator('button:has-text("Generate")').first
            
            if generate_button.is_visible():
                generate_button.click()
                print("   ✓ Generating SSH key...")
                
                # Wait for key generation
                self.page.wait_for_timeout(timeouts.get('sshKeyGeneration', 5000))
                
                # Apply generated key
                apply_button = self.page.locator(f'[data-testid="{ui_config["applyGeneratedButtonTestId"]}"]')
                if not apply_button.is_visible():
                    apply_button = self.page.locator('button:has-text("Apply")').first
                
                if apply_button.is_visible():
                    apply_button.click()
                    print("   ✓ SSH key generated and applied")
                    return True
                    
        except Exception as e:
            print(f"   ⚠ SSH key generation failed: {str(e)}")
        
        return False
    
    def save_vault_configuration(self):
        """Save vault configuration"""
        print("\n9. Saving vault configuration...")
        
        ui_config = self.config['systemVaultConfiguration']['ui']
        timeouts = self.config['systemVaultConfiguration']['timeouts']
        
        # Find save button
        save_button = self.page.locator(f'[data-testid="{ui_config["saveButtonTestId"]}"]')
        
        # Fallback selectors
        if not save_button.is_visible():
            save_selectors = [
                '.ant-modal button:has-text("Save")',
                '.ant-modal button:has-text("OK")',
                '.ant-modal button.ant-btn-primary'
            ]
            
            for selector in save_selectors:
                try:
                    save_button = self.page.locator(selector).first
                    if save_button.is_visible():
                        break
                except:
                    continue
        
        # Check if save button is enabled
        try:
            is_disabled = save_button.is_disabled()
            if is_disabled:
                print("   ⚠ Save button is disabled (required fields may be missing)")
                return False
        except:
            pass
        
        # Click save button
        save_button.click()
        print("   ✓ Save button clicked")
        
        return True
    
    def validate_save(self):
        """Validate vault configuration save"""
        print("\n10. Validating save...")
        
        ui_config = self.config['systemVaultConfiguration']['ui']
        validation_config = self.config['systemVaultConfiguration']['validation']
        timeouts = self.config['systemVaultConfiguration']['timeouts']
        
        success = False
        
        # Method 1: Check if modal closed
        try:
            modal = self.page.locator(ui_config['modalSelector'])
            expect(modal).not_to_be_visible(timeout=timeouts.get('save', 5000))
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
                        if indicator in text:
                            success = True
                            break
            except:
                continue
        
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
            print("System Vault Configuration Test - Smart Version")
            print("=" * 60)
            
            # Setup
            self.setup_browser(playwright)
            
            # Login
            self.login()
            
            # Navigate to System
            self.navigate_to_system()
            
            # Take screenshot of System page
            self.take_screenshot("system_page")
            
            # Open vault configuration
            self.open_vault_configuration()
            
            # Fill required fields
            self.fill_required_fields()
            
            # Generate SSH key
            ssh_generated = self.generate_ssh_key()
            
            # Save vault configuration
            save_clicked = self.save_vault_configuration()
            
            # Wait for API processing
            if save_clicked:
                self.page.wait_for_timeout(2000)
            
            # Validate
            success = self.validate_save() if save_clicked else False
            
            # Take final screenshot
            self.take_screenshot("vault_configured")
            
            # Report result
            print("\n" + "=" * 60)
            if success:
                print("✅ TEST PASSED: Vault configuration saved successfully!")
                print(f"   Vault Type: {self.vault_type}")
                print(f"   SSH Key Generated: {'Yes' if ssh_generated else 'No'}")
            else:
                print("❌ TEST FAILED: Vault configuration could not be saved")
                if not save_clicked:
                    print("   Required fields may be missing")
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
        test = VaultConfigurationTest()
        
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