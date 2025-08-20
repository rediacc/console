#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from logging_utils import StructuredLogger, log_playwright_action


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
    # Create logger for this test
    logger = StructuredLogger("login_test", config=config.get('logging', {}))
    logger.log_test_start("LoginTest")
    test_start_time = time.time()
    
    # Extract configuration values
    base_url = config["baseUrl"]
    browser_config = config["browser"]
    login_config = config["login"]
    credentials = login_config["credentials"]
    timeouts = login_config["timeouts"]
    screenshots = config["screenshots"]
    validation = config["validation"]
    
    logger.info("Configuration loaded", base_url=base_url)
    
    # Launch browser with config settings
    browser = playwright.chromium.launch(
        headless=browser_config["headless"],
        slow_mo=browser_config["slowMo"],
        args=['--start-maximized']  # Tam ekran başlatma argümanı
    )
    context = browser.new_context(
        viewport=None,  # Viewport kısıtlamasını kaldır
        no_viewport=True  # Browser pencere boyutunu kullan
    )
    page = context.new_page()
    
    # Navigate to login page
    login_url = f"{base_url}/console/login"
    print(f"📍 Navigating to: {login_url}")
    page.goto(login_url, wait_until="networkidle")
    
    # Get credentials
    email = credentials["email"]
    password = credentials["password"]
    
    print(f"👤 Logging in as: {email}")
    logger.log_test_step("fill_credentials", "Filling login credentials")
    
    with logger.performance_tracker("fill_login_form"):
        # Wait for and fill login form
        email_input = page.get_by_test_id("login-email-input")
        email_input.wait_for(state="visible", timeout=timeouts["element"])
        email_input.fill(email)
        log_playwright_action(logger, "fill", selector="login-email-input", value_info="email entered")
        
        password_input = page.get_by_test_id("login-password-input")
        password_input.fill(password)
        log_playwright_action(logger, "fill", selector="login-password-input", value_info="***SANITIZED***")
    
    logger.info("Login credentials filled", email=email)
    
    # Submit the form
    logger.log_test_step("submit_login", "Submitting login form")
    submit_button = page.get_by_test_id("login-submit-button")
    
    with logger.performance_tracker("login_submission"):
        submit_button.click()
        log_playwright_action(logger, "click", selector="login-submit-button", element_text="Submit")
    
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
        test_duration_ms = (time.time() - test_start_time) * 1000
        logger.error("Login test failed", error=e, duration_ms=test_duration_ms)
        
        # Take failure screenshot if enabled
        if screenshots["enabled"]:
            screenshot_dir = Path(screenshots["path"])
            screenshot_dir.mkdir(exist_ok=True, parents=True)
            failure_path = screenshot_dir / "login_failed.png"
            page.screenshot(path=str(failure_path))
            print(f"📸 Error screenshot saved as {failure_path}")
            logger.info("Error screenshot captured", path=str(failure_path))
        
        logger.log_test_end("LoginTest", success=False, duration_ms=test_duration_ms)
        # Re-raise the exception
        raise
    
    finally:
        # Clean up
        context.close()
        browser.close()
        logger.info("Browser closed")


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
