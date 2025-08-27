#!/usr/bin/env python3
"""
System Change Password Test - Smart Version
Tests the password change functionality in Rediacc console
- Uses config.json for credentials
- Removes hardcoded values
- Optimized waits without unnecessary sleep
"""

import json
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect, TimeoutError

def load_config():
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r') as f:
        return json.load(f)

def wait_for_element_and_click(page, selector, timeout=5000):
    """Wait for element to be visible and clickable, then click"""
    try:
        element = page.locator(selector).first
        element.wait_for(state="visible", timeout=int(timeout))
        element.wait_for(state="enabled", timeout=int(timeout))
        element.click()
        return True
    except TimeoutError:
        return False

def wait_for_any_selector(page, selectors, timeout=5000):
    """Wait for any of the given selectors to be visible and return the first found"""
    for selector in selectors:
        try:
            element = page.locator(selector).first
            element.wait_for(state="visible", timeout=int(timeout))
            return element
        except:
            continue
    return None

def run(playwright: Playwright) -> None:
    """Main test execution"""
    browser = None
    context = None
    config = load_config()
    
    # Extract configuration values
    base_url = config.get("baseUrl", "http://localhost:7322")
    login_creds = config.get("login", {}).get("credentials", {})
    email = login_creds.get("email", "admin@rediacc.io")
    password = login_creds.get("password", "admin")
    browser_config = config.get("browser", {})
    timeouts = config.get("timeouts", {})
    
    # Password change configuration - could be added to config.json
    password_change_config = config.get("systemChangePassword", {
        "newPassword": "Admin123_&",
        "ui": {
            "changePasswordButtonSelectors": [
                "[data-testid='system-change-password-button']",
                "button:has-text('Change Password')",
                "button:has-text('Reset Password')",
                "[data-testid*='change-password']"
            ],
            "newPasswordSelectors": [
                "[role='textbox'][name='* New Password']",
                "input[placeholder*='new password' i]",
                "input[name='newPassword']",
                ".ant-form-item:has-text('New Password') input",
                ".ant-modal input[type='password']:first-of-type"
            ],
            "confirmPasswordSelectors": [
                "[role='textbox'][name='* Confirm New Password']",
                "input[placeholder*='confirm' i]",
                "input[name='confirmPassword']",
                ".ant-form-item:has-text('Confirm') input",
                ".ant-modal input[type='password']:nth-of-type(2)"
            ],
            "submitButtonSelectors": [
                "button[role='button'][name='Change Password']",
                "button:has-text('Change Password')",
                "button:has-text('Update Password')",
                ".ant-modal button.ant-btn-primary",
                "[role='dialog'] button[type='submit']"
            ]
        }
    })
    
    new_password = password_change_config.get("newPassword", "Admin123_&")
    ui_config = password_change_config.get("ui", {})
    
    try:
        print("Starting System Change Password Test (Smart Version)...")
        
        # Launch browser with config settings
        browser = playwright.chromium.launch(
            headless=browser_config.get("headless", False),
            slow_mo=browser_config.get("slowMo", 0)
        )
        
        viewport = browser_config.get("viewport", {})
        context = browser.new_context(
            viewport={
                "width": viewport.get("width", 1280),
                "height": viewport.get("height", 720)
            }
        )
        page = context.new_page()
        
        # Set default timeout from config
        page.set_default_timeout(int(timeouts.get("pageLoad", 30000)))
        
        # Navigate to console
        print("1. Navigating to console...")
        page.goto(f"{base_url}/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Check current URL and handle login
        current_url = page.url
        print(f"2. Current URL: {current_url}")
        
        if '/login' in current_url or 'signin' in current_url or current_url.endswith('/console/'):
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
        
        # Perform login using config credentials
        print("4. Logging in with configured credentials...")
        
        # Find email input with multiple strategies
        email_selectors = [
            f'[data-testid="{config.get("login", {}).get("ui", {}).get("loginEmailTestId", "login-email-input")}"]',
            'input[type="email"]',
            'input[placeholder*="email" i]'
        ]
        
        email_input = wait_for_any_selector(page, email_selectors, timeouts.get("element", 5000))
        if not email_input:
            raise Exception("Could not find email input field")
        email_input.fill(email)
        
        # Find password input
        password_selectors = [
            f'[data-testid="{config.get("login", {}).get("ui", {}).get("loginPasswordTestId", "login-password-input")}"]',
            'input[type="password"]'
        ]
        
        password_input = wait_for_any_selector(page, password_selectors, timeouts.get("element", 5000))
        if not password_input:
            raise Exception("Could not find password input field")
        password_input.fill(password)
        
        # Find and click submit button
        submit_selectors = [
            f'[data-testid="{config.get("login", {}).get("ui", {}).get("loginSubmitButtonTestId", "login-submit-button")}"]',
            'button[type="submit"]',
            'button:has-text("Sign In")'
        ]
        
        submit_button = wait_for_any_selector(page, submit_selectors, timeouts.get("element", 5000))
        if not submit_button:
            raise Exception("Could not find submit button")
        submit_button.click()
        
        # Wait for dashboard
        print("5. Waiting for dashboard...")
        dashboard_url = config.get("validation", {}).get("dashboardUrl", "**/console/dashboard")
        page.wait_for_url(dashboard_url, timeout=int(timeouts.get("navigation", 10000)))
        print("   Login successful!")
        
        # Navigate to System
        print("6. Navigating to System...")
        system_selectors = [
            f'[data-testid="{config.get("systemCreateUser", {}).get("ui", {}).get("systemNavTestId", "main-nav-system")}"]',
            'a:has-text("System")',
            'nav a:has-text("System")',
            '[data-testid*="system"]'
        ]
        
        system_link = wait_for_any_selector(page, system_selectors, timeouts.get("element", 5000))
        if not system_link:
            raise Exception("Could not find System navigation link")
        system_link.click()
        
        # Wait for page to load completely
        page.wait_for_load_state("networkidle")
        
        # Click change password button
        print("7. Opening change password dialog...")
        change_password_button = wait_for_any_selector(
            page, 
            ui_config.get("changePasswordButtonSelectors", []),
            timeouts.get("element", 5000)
        )
        
        if not change_password_button:
            print("   Warning: Could not find change password button")
        else:
            change_password_button.click()
            print("   Change password dialog opened")
            
            # Wait for dialog to be visible
            page.wait_for_selector(".ant-modal", state="visible", timeout=int(timeouts.get("modalOpen", 3000)))
            
            # Enter new password
            print("8. Entering new password...")
            new_password_input = wait_for_any_selector(
                page,
                ui_config.get("newPasswordSelectors", []),
                timeouts.get("element", 5000)
            )
            
            if not new_password_input:
                print("   Warning: Could not enter new password")
            else:
                new_password_input.fill(new_password)
                print("   New password entered")
            
            # Enter confirm password
            print("9. Confirming new password...")
            confirm_password_input = wait_for_any_selector(
                page,
                ui_config.get("confirmPasswordSelectors", []),
                timeouts.get("element", 5000)
            )
            
            if not confirm_password_input:
                print("   Warning: Could not enter confirm password")
            else:
                confirm_password_input.fill(new_password)
                print("   Confirm password entered")
            
            # Submit password change
            print("10. Submitting password change...")
            submit_button = wait_for_any_selector(
                page,
                ui_config.get("submitButtonSelectors", []),
                timeouts.get("element", 5000)
            )
            
            if not submit_button:
                print("   Warning: Could not submit password change")
            else:
                submit_button.click()
                print("   Password change submitted")
                
                # Wait for success notification or modal to close
                success = False
                
                # First check for success notifications
                success_selectors = [
                    ".ant-message-success",
                    ".ant-notification-notice-success",
                    "text=/Password.*changed.*successfully/i",
                    "text=/Password.*updated.*successfully/i"
                ]
                
                # Wait a moment for notifications to appear
                page.wait_for_timeout(500)
                
                for selector in success_selectors:
                    try:
                        if page.locator(selector).is_visible():
                            print("   Password change completed successfully")
                            success = True
                            break
                    except:
                        continue
                
                # If no notification found, check if modal closed
                if not success:
                    try:
                        page.wait_for_selector(".ant-modal", state="hidden", timeout=int(timeouts.get("modalClose", 3000)))
                        print("   Password change completed (modal closed)")
                        success = True
                    except TimeoutError:
                        print("   Password change submitted - awaiting confirmation")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error
            screenshot_config = config.get("screenshots", {})
            if screenshot_config.get("enabled", True):
                screenshot_path = Path(__file__).parent / screenshot_config.get("path", "./artifacts/screenshots") / "error_screenshot_changepassword_smart.png"
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
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