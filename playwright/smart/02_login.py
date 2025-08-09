#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def load_config(config_path="config.json"):
    """Load configuration from JSON file"""
    # Check multiple possible locations for config file
    possible_paths = [
        Path(config_path),  # Current directory or absolute path
        Path(__file__).parent / config_path,  # Same directory as script
        Path(__file__).parent.parent / config_path,  # Parent directory (playwright)
        Path.cwd() / config_path,  # Current working directory
    ]
    
    for path in possible_paths:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    # If no config file found, raise error
    raise FileNotFoundError(
        f"Configuration file not found. Tried locations:\n" + 
        "\n".join(f"  - {p}" for p in possible_paths)
    )


def run(playwright: Playwright, config: dict) -> None:
    """Run the login automation with configuration"""
    
    # Extract configuration values
    base_url = config["baseUrl"]
    browser_config = config["browser"]
    login_config = config["login"]
    credentials = login_config["credentials"]
    timeouts = login_config["timeouts"]
    screenshots = config["screenshots"]
    validation = config["validation"]
    
    # Launch browser with config settings
    browser = playwright.chromium.launch(
        headless=browser_config["headless"],
        slow_mo=browser_config["slowMo"]
    )
    context = browser.new_context()
    page = context.new_page()
    
    # Navigate to login page
    login_url = f"{base_url}/console/login"
    print(f"📍 Navigating to: {login_url}")
    page.goto(login_url, wait_until="networkidle")
    
    # Get credentials
    email = credentials["email"]
    password = credentials["password"]
    
    print(f"👤 Logging in as: {email}")
    
    # Wait for and fill login form
    email_input = page.get_by_test_id("login-email-input")
    email_input.wait_for(state="visible", timeout=timeouts["element"])
    email_input.fill(email)
    
    password_input = page.get_by_test_id("login-password-input")
    password_input.fill(password)
    
    # Submit the form
    submit_button = page.get_by_test_id("login-submit-button")
    submit_button.click()
    
    # Validate successful login
    try:
        # Wait for dashboard URL
        dashboard_url = validation["dashboardUrl"]
        page.wait_for_url(dashboard_url, timeout=timeouts["navigation"])
        
        # Check for expected elements
        expected_elements = validation["expectedElements"]
        for element in expected_elements:
            selector = element["selector"]
            description = element["description"]
            page.wait_for_selector(
                selector, 
                state="visible", 
                timeout=timeouts["element"]
            )
            print(f"  ✓ Found: {description}")
        
        # Check for user email in the page (dynamic selector)
        user_selector = validation["userEmailSelector"].replace("${email}", email)
        page.wait_for_selector(
            user_selector, 
            state="visible", 
            timeout=timeouts["element"]
        )
        print(f"  ✓ User verified: {email}")
        
        # Wait for network idle
        page.wait_for_load_state("networkidle", timeout=timeouts["network"])
        
        print("✅ Login successful! Dashboard loaded completely.")
        
        # Take success screenshot if enabled
        if screenshots["enabled"]:
            screenshot_dir = Path(screenshots["path"])
            screenshot_dir.mkdir(exist_ok=True, parents=True)
            success_path = screenshot_dir / "login_success.png"
            page.screenshot(path=str(success_path))
            print(f"📸 Screenshot saved as {success_path}")
        
    except Exception as e:
        print(f"❌ Login failed or timeout occurred: {e}")
        
        # Take failure screenshot if enabled
        if screenshots["enabled"]:
            screenshot_dir = Path(screenshots["path"])
            screenshot_dir.mkdir(exist_ok=True, parents=True)
            failure_path = screenshot_dir / "login_failed.png"
            page.screenshot(path=str(failure_path))
            print(f"📸 Error screenshot saved as {failure_path}")
        
        # Re-raise the exception
        raise
    
    finally:
        # Clean up
        context.close()
        browser.close()


def main():
    """Main entry point"""
    # Allow config file path as command line argument
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    
    try:
        # Load configuration
        config = load_config(config_file)
        print(f"📋 Configuration loaded from: {config_file}")
        
        # Run playwright with config
        with sync_playwright() as playwright:
            run(playwright, config)
            
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
