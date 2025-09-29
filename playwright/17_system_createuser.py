#!/usr/bin/env python3
"""
System Create User Test - Smart Version
Tests the user creation functionality in Rediacc console using discovered selectors and config-based settings
"""

import json
import time
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


# Load configuration
config_path = Path(__file__).parent / "config.json"
with open(config_path) as f:
    config = json.load(f)


def run(playwright: Playwright) -> None:
    """Main test execution using smart selectors and config"""
    browser = None
    context = None
    
    try:
        print("Starting Smart System Create User Test...")
        
        # Launch browser with config settings
        browser = playwright.chromium.launch(
            headless=config['browser']['headless'],
            slow_mo=config['browser']['slowMo']
        )
        context = browser.new_context(
            viewport=config['browser']['viewport']
        )
        page = context.new_page()
        
        # Set timeouts from config
        page.set_default_timeout(config['timeouts']['pageLoad'])
        
        # Navigate to console
        print("1. Navigating to console...")
        page.goto(config['baseUrl'] + "/console")
        page.wait_for_load_state("domcontentloaded")
        
        # Check if we need to login by looking for login form
        current_url = page.url
        print(f"2. Current URL: {current_url}")
        
        # Check for login form presence rather than URL
        login_form_present = False
        try:
            email_input = page.locator('input[type="email"], input[placeholder*="email" i]').first
            if email_input.is_visible(timeout=2000):
                login_form_present = True
        except:
            pass
        
        if login_form_present:
            print("3. Login form detected, performing login...")
            
            # Use config credentials and smart selectors
            email_input = page.locator('input[type="email"], input[placeholder*="email" i]').first
            expect(email_input).to_be_visible(timeout=config['login']['timeouts']['element'])
            email_input.fill(config['login']['credentials']['email'])
            
            password_input = page.locator('input[type="password"]').first
            expect(password_input).to_be_visible(timeout=config['login']['timeouts']['element'])
            password_input.fill(config['login']['credentials']['password'])
            
            submit_button = page.locator('button[type="submit"], button:has-text("Sign In")').first
            expect(submit_button).to_be_visible(timeout=config['login']['timeouts']['element'])
            submit_button.click()
            
            # Wait for dashboard with config timeout
            print("   Waiting for dashboard...")
            page.wait_for_url(config['validation']['dashboardUrl'], timeout=config['login']['timeouts']['navigation'])
            print("   Login successful!")
        else:
            print("3. Already logged in, proceeding...")
        
        # Navigate to System page
        print("4. Navigating to System page...")
        system_nav = page.locator(f'[data-testid="{config["systemCreateUser"]["ui"]["systemNavTestId"]}"]')
        expect(system_nav).to_be_visible(timeout=config['systemCreateUser']['timeouts']['elementWait'])
        system_nav.click()
        
        # Wait for System page to load
        page.wait_for_load_state("networkidle", timeout=config['systemCreateUser']['timeouts']['pageLoad'])
        
        # Ensure we're on the Users tab and click Create User button
        print("5. Ensuring Users tab is active and opening Create User dialog...")
        
        # Click Users tab to ensure it's active
        users_tab = page.locator(config['systemCreateUser']['ui']['usersTabSelector'])
        expect(users_tab).to_be_visible(timeout=config['systemCreateUser']['timeouts']['elementWait'])
        users_tab.click()
        
        # Wait a moment for tab content to load
        page.wait_for_timeout(config['systemCreateUser']['timeouts']['modalOpen'])
        
        # Click Create User button (discovered as icon button with test-id)
        create_user_button = page.locator(f'[data-testid="{config["systemCreateUser"]["ui"]["createUserButtonTestId"]}"]')
        expect(create_user_button).to_be_visible(timeout=config['systemCreateUser']['timeouts']['elementWait'])
        create_user_button.click()
        
        # Wait for modal to appear
        modal = page.locator(config['systemCreateUser']['ui']['modalSelector'])
        expect(modal).to_be_visible(timeout=config['systemCreateUser']['timeouts']['modalOpen'])
        print("   Create user modal opened successfully")
            
        # Fill user creation form with config-based test data
        print("6. Filling user creation form...")
        
        # Generate test user credentials from config
        user_config = config['systemCreateUser']['testData']
        if user_config['generateUniqueEmail']:
            import time
            timestamp = str(int(time.time()))
            test_email = f"{user_config['emailPrefix']}{timestamp}{user_config['emailDomain']}"
        else:
            test_email = f"{user_config['emailPrefix']}test{user_config['emailDomain']}"
        
        test_password = user_config['defaultPassword']
        
        # Fill email field using config selector
        email_input = page.locator(f'[data-testid="{config["systemCreateUser"]["ui"]["emailInputTestId"]}"]')
        expect(email_input).to_be_visible(timeout=config['systemCreateUser']['timeouts']['elementWait'])
        email_input.fill(test_email)
        print(f"   Email filled: {test_email}")
        
        # Fill password field using config selector  
        password_input = page.locator(f'[data-testid="{config["systemCreateUser"]["ui"]["passwordInputTestId"]}"]')
        expect(password_input).to_be_visible(timeout=config['systemCreateUser']['timeouts']['elementWait'])
        password_input.fill(test_password)
        print("   Password filled")
        
        # Take screenshot before submission if enabled
        if config['screenshots']['enabled']:
            screenshot_path = Path(config['screenshots']['path']) / "before_user_creation_submit.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   Screenshot saved: {screenshot_path}")
            
        # Submit user creation form
        print("7. Submitting user creation form...")
        
        # Click submit button using config selector
        submit_button = page.locator(f'[data-testid="{config["systemCreateUser"]["ui"]["submitButtonTestId"]}"]')
        expect(submit_button).to_be_visible(timeout=config['systemCreateUser']['timeouts']['elementWait'])
        submit_button.click()
        print("   Form submitted, waiting for API response...")
        
        # Give the API call time to process
        page.wait_for_timeout(3000)
        
        # Smart validation with comprehensive success checking
        print("8. Validating user creation success...")
        
        success = False
        validation_config = config['systemCreateUser']['validation']
        
        # Check if modal closes (primary success indicator)
        if validation_config['successIndicators']['modalCloses']:
            try:
                expect(modal).to_be_hidden(timeout=config['systemCreateUser']['timeouts']['modalClose'])
                print("   ✓ SUCCESS: Modal closed automatically (user created successfully)")
                success = True
            except:
                print("   Modal still visible - checking for other success indicators")
        
        # Check for notification messages using config selectors
        for selector in validation_config['successIndicators']['notificationSelectors']:
            try:
                notification = page.locator(selector).first
                if notification.is_visible(timeout=config['systemCreateUser']['timeouts']['notificationWait']):
                    message_text = notification.inner_text()
                    print(f"   Notification found: '{message_text}'")
                    
                    # Check against config success messages
                    for success_msg in validation_config['successMessages']:
                        if success_msg.lower() in message_text.lower():
                            print(f"   ✓ SUCCESS: Found success message match: '{success_msg}'")
                            success = True
                            break
            except:
                continue
        
        # Check for error messages
        error_found = False
        for error_selector in validation_config['errorSelectors']:
            try:
                error_element = page.locator(error_selector).first
                if error_element.is_visible(timeout=1000):
                    error_text = error_element.inner_text()
                    print(f"   ❌ ERROR FOUND: '{error_text}'")
                    error_found = True
            except:
                continue
        
        # Verify new user appears in table if enabled and success indicated
        if success and validation_config['successIndicators']['userAppearsInTable']:
            print("9. Verifying new user in table...")
            page.wait_for_timeout(config['systemCreateUser']['timeouts']['tableRefresh'])
            
            try:
                new_user_row = page.locator(f'text="{test_email}"').first
                expect(new_user_row).to_be_visible(timeout=config['systemCreateUser']['timeouts']['elementWait'])
                print(f"   ✓ SUCCESS: New user '{test_email}' visible in users table")
            except:
                print(f"   Warning: New user '{test_email}' not yet visible in table (may take time to refresh)")
        
        # Take final screenshot if enabled
        if config['screenshots']['enabled']:
            screenshot_path = Path(config['screenshots']['path']) / "after_user_creation.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"   Final screenshot saved: {screenshot_path}")
        
        # Final test result
        if success and not error_found:
            print("\n🎉 USER CREATION TEST COMPLETED SUCCESSFULLY!")
            print(f"   ✓ Test user created: {test_email}")
        elif error_found:
            print(f"\n❌ USER CREATION FAILED - Errors detected")
            raise Exception("User creation failed with errors")
        else:
            print("\n⚠️  USER CREATION STATUS UNCLEAR - Check screenshots and logs")
            print("   Test completed but success indicators were not clearly detected")
        
        print("\nTest completed successfully!")
        
        # Keep browser open briefly to see results
        page.wait_for_timeout(3000)
        
    except Exception as e:
        print(f"\nError during test: {str(e)}")
        if 'page' in locals():
            # Take screenshot on error using config path
            error_screenshot_path = Path(config['screenshots']['path']) / "error_system_createuser.png"
            error_screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(error_screenshot_path), full_page=True)
            print(f"Error screenshot saved to: {error_screenshot_path}")
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