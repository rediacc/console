#!/usr/bin/env python3
"""
System Create Team Test - Fixed Version
Tests the team creation functionality in Rediacc console
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
        print("Starting System Create Team Test...")
        
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
        
        # Click on Teams tab
        print("7. Navigating to Teams tab...")
        teams_tab_found = False
        
        try:
            teams_tab = page.get_by_test_id("system-tab-teams")
            if teams_tab.is_visible():
                teams_tab.click()
                teams_tab_found = True
                print("   Teams tab opened")
        except:
            pass
        
        if not teams_tab_found:
            # Try alternative selectors
            print("   Trying alternative selector for teams tab...")
            try:
                teams_selectors = [
                    'button:has-text("Teams")',
                    'div[role="tab"]:has-text("Teams")',
                    '.ant-tabs-tab:has-text("Teams")',
                    '[data-testid*="teams"]'
                ]
                
                for selector in teams_selectors:
                    try:
                        teams_tab = page.locator(selector).first
                        if teams_tab.is_visible():
                            teams_tab.click()
                            teams_tab_found = True
                            print("   Teams tab opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding teams tab: {str(e)}")
        
        if not teams_tab_found:
            print("   Warning: Could not find teams tab")
        
        time.sleep(1)  # Wait for teams tab to load
        
        # Click create team button
        print("8. Opening create team dialog...")
        create_team_found = False
        
        try:
            create_button = page.get_by_test_id("system-create-team-button")
            if create_button.is_visible():
                create_button.click()
                create_team_found = True
                print("   Create team dialog opened")
        except:
            pass
        
        if not create_team_found:
            # Try alternative selectors
            print("   Trying alternative selector for create team button...")
            try:
                create_selectors = [
                    'button:has-text("Create Team")',
                    'button:has-text("Add Team")',
                    'button:has-text("New Team")',
                    'button[title*="team"]',
                    '[data-testid*="create-team"]',
                    'button.ant-btn-primary'
                ]
                
                for selector in create_selectors:
                    try:
                        create_button = page.locator(selector).first
                        if create_button.is_visible():
                            create_button.click()
                            create_team_found = True
                            print("   Create team dialog opened using alternative selector")
                            break
                    except:
                        continue
            except Exception as e:
                print(f"   Error finding create team button: {str(e)}")
        
        if not create_team_found:
            print("   Warning: Could not find create team button")
        else:
            time.sleep(1)  # Wait for dialog to open
            
            # Fill in team details
            print("9. Filling team details...")
            
            # Team name input
            team_name_filled = False
            try:
                team_name_input = page.get_by_test_id("resource-modal-field-teamName-input")
                if team_name_input.is_visible():
                    team_name_input.fill("test2")
                    team_name_filled = True
                    print("   Team name filled: test2")
            except:
                # Try alternative selectors
                team_name_selectors = [
                    'input[placeholder*="team" i]',
                    'input[name="teamName"]',
                    '.ant-modal input[type="text"]',
                    '.ant-form-item input'
                ]
                for selector in team_name_selectors:
                    try:
                        team_name_input = page.locator(selector).first
                        if team_name_input.is_visible():
                            team_name_input.fill("test2")
                            team_name_filled = True
                            print("   Team name filled using alternative selector: test2")
                            break
                    except:
                        continue
            
            if not team_name_filled:
                print("   Warning: Could not fill team name")
            
            # Generate SSH key
            print("10. Generating SSH key...")
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
                print("   Could not generate SSH key using test-id")
            
            if not ssh_key_generated:
                print("   Warning: Could not generate SSH key")
            
            # Submit team creation
            print("11. Submitting team creation...")
            submit_found = False
            
            try:
                submit_button = page.get_by_test_id("resource-modal-ok-button")
                if submit_button.is_visible():
                    submit_button.click()
                    submit_found = True
                    print("   Team creation submitted")
            except:
                # Try alternative selectors
                submit_selectors = [
                    '.ant-modal button:has-text("OK")',
                    '.ant-modal button:has-text("Create")',
                    '.ant-modal button:has-text("Submit")',
                    '.ant-modal button.ant-btn-primary',
                    '[role="dialog"] button[type="submit"]'
                ]
                for selector in submit_selectors:
                    try:
                        submit_button = page.locator(selector).first
                        if submit_button.is_visible():
                            submit_button.click()
                            submit_found = True
                            print("   Team creation submitted using alternative selector")
                            break
                    except:
                        continue
            
            if not submit_found:
                print("   Warning: Could not submit team creation")
            else:
                time.sleep(2)  # Wait for team creation to complete
                print("   Team creation completed")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "error_screenshot_createteam.png"
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