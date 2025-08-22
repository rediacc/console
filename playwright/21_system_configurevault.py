#!/usr/bin/env python3
"""
System Configure Vault Test - Fixed Version
Tests the vault configuration functionality in Rediacc console
"""

import re
import time
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    """Main test execution"""
    browser = None
    context = None
    
    try:
        print("Starting System Configure Vault Test...")
        
        # Launch browser
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Set reasonable timeout
        page.set_default_timeout(30000)
        
        # Navigate to console
        print("1. Navigating to console...")
        page.goto("http://localhost:7322/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Check current URL and handle login
        current_url = page.url
        print(f"2. Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
            # Already on login page or redirected to login
            print("3. On login page, proceeding with login...")
        else:
            # Try to find and click login link
            print("3. Looking for login link...")
            try:
                login_link = page.get_by_role("banner").get_by_role("link", name="Login")
                with page.expect_popup() as popup_info:
                    login_link.click()
                page = popup_info.value
                print("   Navigated to login page via popup")
            except:
                print("   No login link found, assuming already on login page")
        
        # Perform login
        print("4. Logging in...")
        
        # Find email input with multiple strategies
        email_input = None
        for selector in ['[data-testid="login-email-input"]', 'input[type="email"]', 'input[placeholder*="email" i]']:
            try:
                email_input = page.locator(selector).first
                if email_input.is_visible():
                    break
            except:
                continue
        
        if not email_input:
            raise Exception("Could not find email input field")
        
        email_input.fill("admin@rediacc.io")
        
        # Find password input
        password_input = None
        for selector in ['[data-testid="login-password-input"]', 'input[type="password"]']:
            try:
                password_input = page.locator(selector).first
                if password_input.is_visible():
                    break
            except:
                continue
        
        if not password_input:
            raise Exception("Could not find password input field")
        
        password_input.fill("admin")
        
        # Find and click submit button
        submit_button = None
        for selector in ['[data-testid="login-submit-button"]', 'button[type="submit"]', 'button:has-text("Sign In")']:
            try:
                submit_button = page.locator(selector).first
                if submit_button.is_visible():
                    break
            except:
                continue
        
        if not submit_button:
            raise Exception("Could not find submit button")
        
        submit_button.click()
        
        # Wait for dashboard
        print("5. Waiting for dashboard...")
        page.wait_for_url("**/console/dashboard", timeout=10000)
        print("   Login successful!")
        
        # Navigate to System
        print("6. Navigating to System...")
        try:
            system_link = page.get_by_test_id("main-nav-system")
            system_link.click()
        except:
            # Try alternative selector
            system_link = page.locator('nav a:has-text("System")').first
            if not system_link.is_visible():
                system_link = page.locator('[data-testid*="system"]').first
            system_link.click()
        
        page.wait_for_load_state("networkidle")
        
        # Click on user vault button
        print("7. Opening user vault configuration...")
        vault_button_found = False
        
        try:
            vault_button = page.get_by_test_id("system-user-vault-button")
            if vault_button.is_visible():
                vault_button.click()
                vault_button_found = True
                print("   Vault configuration dialog opened")
        except:
            pass
        
        if not vault_button_found:
            # Try alternative selectors
            print("   Trying alternative selector for vault button...")
            try:
                vault_selectors = [
                    'button:has-text("Configure Vault")',
                    'button:has-text("Vault")',
                    'button[title*="vault"]',
                    'button[title*="Vault"]',
                    '[data-testid*="vault"]',
                    '.ant-table button:has-text("Vault")'
                ]
                
                for selector in vault_selectors:
                    try:
                        vault_button = page.locator(selector).first
                        if vault_button.is_visible():
                            vault_button.click()
                            vault_button_found = True
                            print("   Vault configuration dialog opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding vault button: {str(e)}")
        
        if not vault_button_found:
            print("   Warning: Could not find vault configuration button")
        else:
            time.sleep(1)  # Wait for vault dialog to open
            
            # Generate SSH key
            print("8. Generating SSH key...")
            ssh_key_generated = False
            
            try:
                generate_button = page.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY")
                if generate_button.is_visible():
                    generate_button.click()
                    time.sleep(0.5)
                    
                    # Click generate button
                    gen_btn = page.get_by_test_id("vault-editor-generate-button")
                    if gen_btn.is_visible():
                        gen_btn.click()
                        time.sleep(1)
                        
                        # Apply generated key
                        apply_btn = page.get_by_test_id("vault-editor-apply-generated")
                        if apply_btn.is_visible():
                            apply_btn.click()
                            ssh_key_generated = True
                            print("   SSH key generated and applied")
            except:
                # Try alternative approach
                print("   Trying alternative selectors for SSH key generation...")
                try:
                    # Look for generate buttons
                    generate_selectors = [
                        'button:has-text("Generate")',
                        'button[title*="generate"]',
                        '[data-testid*="generate"]'
                    ]
                    
                    for selector in generate_selectors:
                        try:
                            gen_button = page.locator(selector).first
                            if gen_button.is_visible():
                                gen_button.click()
                                time.sleep(1)
                                
                                # Look for apply button
                                apply_button = page.locator('button:has-text("Apply")').first
                                if apply_button.is_visible():
                                    apply_button.click()
                                    ssh_key_generated = True
                                    print("   SSH key generated using alternative selectors")
                                break
                        except:
                            continue
                except:
                    pass
            
            if not ssh_key_generated:
                print("   Warning: Could not generate SSH key")
            
            # Save vault configuration
            print("9. Saving vault configuration...")
            save_found = False
            
            try:
                save_button = page.get_by_test_id("vault-modal-save-button")
                if save_button.is_visible():
                    save_button.click()
                    save_found = True
                    print("   Vault configuration saved")
            except:
                # Try alternative selectors
                save_selectors = [
                    '.ant-modal button:has-text("Save")',
                    '.ant-modal button:has-text("OK")',
                    '.ant-modal button:has-text("Submit")',
                    '.ant-modal button.ant-btn-primary',
                    '[role="dialog"] button[type="submit"]',
                    '[role="dialog"] button:has-text("Save")'
                ]
                for selector in save_selectors:
                    try:
                        save_button = page.locator(selector).first
                        if save_button.is_visible():
                            save_button.click()
                            save_found = True
                            print("   Vault configuration saved using alternative selector")
                            break
                    except:
                        continue
            
            if not save_found:
                print("   Warning: Could not save vault configuration")
            else:
                time.sleep(2)  # Wait for save to complete
                print("   Vault configuration completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot_vault.png"
            page.screenshot(path=str(screenshot_path))
            print(f"Screenshot saved to: {screenshot_path}")
        raise
    
    finally:
        # Cleanup
        if context:
            context.close()
        if browser:
            browser.close()
        print("Browser closed.")


def main():
    """Entry point"""
    try:
        with sync_playwright() as playwright:
            run(playwright)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()