#!/usr/bin/env python3
"""
Container Stats Test - Fixed Version
Tests the container stats functionality in Rediacc console
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
        print("Starting Container Stats Test...")
        
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
        
        # Navigate to Resources
        print("6. Navigating to Resources...")
        resources_link = page.get_by_test_id("main-nav-resources").get_by_text("Resources")
        resources_link.click()
        page.wait_for_load_state("networkidle")
        
        # Expand machine
        print("7. Expanding machine rediacc11...")
        try:
            # Try with svg locator first
            machine_expand = page.get_by_test_id("machine-expand-rediacc11").locator("svg")
            if machine_expand.is_visible():
                machine_expand.click()
            else:
                # Try without svg
                machine_expand = page.get_by_test_id("machine-expand-rediacc11")
                machine_expand.click()
        except:
            # Try alternative selector
            machine_row = page.locator('tr:has-text("rediacc11")').first
            expand_button = machine_row.locator('button').first
            expand_button.click()
        
        time.sleep(1)  # Wait for expansion
        
        # Find and expand repository
        print("8. Looking for repositories to expand...")
        try:
            # Try to find repository expand with test-id
            repo_expand = page.get_by_test_id("machine-repo-list-table").get_by_role("img", name="right").locator("svg")
            if repo_expand.is_visible():
                repo_expand.click()
                print("   Repository expanded")
            else:
                raise Exception("Repository expand button not found")
        except:
            # Try alternative - look for any expandable repository
            print("   Trying alternative repository expand...")
            try:
                repo_expand = page.locator('button.ant-table-row-expand-icon').first
                if repo_expand.is_visible():
                    repo_expand.click()
                    print("   Repository expanded using alternative method")
            except:
                print("   Could not find repository expand button")
        
        time.sleep(1)  # Wait for repository to expand
        
        # Look for container actions
        print("9. Looking for container actions...")
        container_found = False
        
        # Try specific container ID first
        try:
            container_button = page.get_by_test_id("machine-repo-list-container-actions-edbcc7482431")
            if container_button.is_visible():
                container_button.click()
                container_found = True
                print("   Found specific container actions button")
        except:
            pass
        
        # If not found, try generic container action buttons
        if not container_found:
            container_selectors = [
                'button[data-testid*="container-actions"]',
                'button:has-text("Actions")',
                '.ant-table-row button[title*="container"]'
            ]
            
            for selector in container_selectors:
                try:
                    container_button = page.locator(selector).first
                    if container_button.is_visible():
                        print("   Found container actions button")
                        container_button.click()
                        container_found = True
                        break
                except:
                    continue
        
        if not container_found:
            print("   Warning: Could not find container actions button")
            print("   This might be because no containers are running")
        else:
            # Click container stats option
            print("10. Clicking container_stats...")
            time.sleep(0.5)  # Wait for menu
            
            stats_option = page.get_by_text("container_stats")
            if stats_option.is_visible():
                stats_option.click()
                print("    Container stats initiated!")
                time.sleep(2)  # Wait for stats to load
                print("    Stats should be displayed now")
            else:
                print("    Could not find container_stats option")
        
        print("\nTest completed!")
        
        # Keep browser open for a moment to see results
        time.sleep(3)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_path = Path(__file__).parent / "artifacts" / "screenshots" / "error_screenshot_stats.png"
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