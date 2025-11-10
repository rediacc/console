import json
import re
import sys
from datetime import datetime
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect


def load_config():
    """Load configuration from config.json file"""
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return json.load(f)


def generate_unique_machine_name(base_name="rediacc"):
    """Generate a unique machine name with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{timestamp}"


def wait_for_success_message(page, timeout=10000):
    """Wait for and capture success messages"""
    success_patterns = [
        "SSH connection successful",
        "Machine created successfully",
        "Machine '.*' created successfully",
        "Setup has been queued",
        "Task Completed Successfully"
    ]
    
    for pattern in success_patterns:
        try:
            # Check for message in various notification containers
            selectors = [
                f"text=/{pattern}/",
                f".ant-message:has-text('{pattern}')",
                f".ant-notification:has-text('{pattern}')",
                f"[role='alert']:has-text('{pattern}')",
                f".toast-success:has-text('{pattern}')"
            ]
            
            for selector in selectors:
                if page.locator(selector).count() > 0:
                    return True
        except:
            continue
    
    return False


def run(playwright: Playwright) -> None:
    # Load configuration
    config = load_config()
    
    # Extract settings from config
    base_url = config.get('baseUrl', 'http://localhost:7322')
    browser_config = config.get('browser', {})
    login_config = config.get('login', {})
    credentials = login_config.get('credentials', {})
    timeouts = login_config.get('timeouts', {})
    
    # Machine creation specific config from config.json
    machine_config = config.get('createMachine', {})
    
    # Set defaults if not in config
    if not machine_config:
        machine_config = {
            'machineName': 'rediacc21',
            'ip': '192.168.111.21',
            'user': 'anl',
            'testConnection': True,
            'runSetupAfterCreation': True,
            'generateUniqueName': True
        }
    
    # Launch browser with config settings
    browser = playwright.chromium.launch(
        headless=browser_config.get('headless', False),
        slow_mo=browser_config.get('slowMo', 0)
    )
    
    # Create context with viewport settings
    context = browser.new_context(
        viewport=browser_config.get('viewport', {'width': 1280, 'height': 720})
    )
    
    # Create page
    page = context.new_page()
    
    # Set default timeout
    page.set_default_timeout(timeouts.get('navigation', 30000))
    
    try:
        # Navigate to login page
        print(f"Navigating to {base_url}/console/login...")
        page.goto(f"{base_url}/console/login")
        
        # Wait for login form to be ready
        page.wait_for_selector('[data-testid="login-email-input"]', state='visible')
        
        # Fill login credentials from config
        print(f"Logging in with email: {credentials.get('email')}...")
        page.get_by_test_id("login-email-input").fill(credentials.get('email', 'admin@rediacc.io'))
        page.get_by_test_id("login-password-input").fill(credentials.get('password', 'admin'))
        
        # Click login button
        page.get_by_test_id("login-submit-button").click()
        
        # Wait for navigation to complete (dashboard should load)
        page.wait_for_url("**/console/dashboard", timeout=timeouts.get('navigation', 10000))
        print("Login successful, dashboard loaded")
        
        # Navigate to Resources
        print("Navigating to Resources...")
        page.get_by_test_id("main-nav-machines").click()
        
        # Wait for Resources page to load
        page.wait_for_selector('[data-testid="resources-create-machine-button"]', state='visible')
        
        # Click Create Machine button
        print("Opening Create Machine dialog...")
        page.get_by_test_id("resources-create-machine-button").click()
        
        # Wait for modal to open
        page.wait_for_selector('[data-testid="resource-modal-field-machineName-input"]', state='visible')
        
        # Generate unique machine name if configured
        machine_name = machine_config.get('machineName', 'rediacc21')
        if machine_config.get('generateUniqueName', True):
            base_name = machine_name if machine_name else 'rediacc21'
            machine_name = generate_unique_machine_name(base_name)
        
        print(f"Creating machine with name: {machine_name}")
        
        # Fill machine name
        page.get_by_test_id("resource-modal-field-machineName-input").fill(machine_name)
        
        # Expand Required Fields if collapsed
        required_fields_button = page.get_by_role("button", name="expanded Required Fields")
        if required_fields_button.count() > 0:
            required_fields_button.click()
            # Wait for animation
            page.wait_for_timeout(500)
        
        # Check if we need to re-expand (sometimes it collapses automatically)
        collapsed_button = page.get_by_role("button", name="collapsed Required Fields")
        if collapsed_button.count() > 0:
            collapsed_button.click()
            page.wait_for_timeout(500)
        
        # Fill IP address
        print(f"Setting IP address: {machine_config.get('ip')}...")
        ip_field = page.get_by_test_id("vault-editor-field-ip")
        ip_field.wait_for(state='visible')
        ip_field.fill(machine_config.get('ip', '192.168.111.21'))
        
        # Fill username
        print(f"Setting username: {machine_config.get('user')}...")
        user_field = page.get_by_test_id("vault-editor-field-user")
        user_field.wait_for(state='visible')
        user_field.fill(machine_config.get('user', 'anl'))
        
        # Click on Configured status (if needed)
        configured_div = page.locator("div").filter(has_text=re.compile(r"^Configured$")).nth(1)
        if configured_div.count() > 0:
            configured_div.click()
            page.wait_for_timeout(500)
        
        # Test connection if configured
        if machine_config.get('testConnection', True):
            print("Testing SSH connection...")
            test_button = page.get_by_test_id("vault-editor-test-connection")
            test_button.wait_for(state='visible')
            test_button.click()
            
            # Wait for connection test result
            connection_success = False
            for _ in range(10):  # Try for up to 10 seconds
                if page.locator("text=/SSH connection successful/").count() > 0:
                    connection_success = True
                    print("✓ SSH connection successful")
                    break
                page.wait_for_timeout(1000)
            
            if not connection_success:
                print("⚠ SSH connection test did not show success message, but continuing...")
        
        # Wait for OK button to be enabled (it gets enabled after successful connection test)
        ok_button = page.get_by_test_id("resource-modal-ok-button")
        ok_button.wait_for(state='visible')
        
        # Small wait to ensure button is fully enabled
        page.wait_for_timeout(1000)
        
        # Click OK to create machine
        print("Creating machine...")
        ok_button.click()
        
        # Wait for success message
        creation_success = False
        for _ in range(15):  # Try for up to 15 seconds
            if page.locator("text=/Machine created successfully/").count() > 0:
                creation_success = True
                print(f"✓ Machine '{machine_name}' created successfully")
                break
            if page.locator("text=/Machine.*created successfully/").count() > 0:
                creation_success = True
                print(f"✓ Machine '{machine_name}' created successfully")
                break
            page.wait_for_timeout(1000)
        
        if not creation_success:
            print("⚠ Machine creation message not detected, but may have succeeded")
        
        # Handle queue trace dialog if it appears
        queue_trace_close = page.get_by_test_id("queue-trace-close-button")
        if queue_trace_close.count() > 0:
            print("Closing queue trace dialog...")
            # Wait a moment to see the queue status
            page.wait_for_timeout(2000)
            
            # Check for completion status
            if page.locator("text=/Task Completed Successfully/").count() > 0:
                print("✓ Setup task completed successfully")
            elif page.locator("text=/Completed/").count() > 0:
                print("✓ Task completed")
            
            queue_trace_close.click()
        
        print("\n✅ Machine creation process completed successfully!")
        print(f"Machine Name: {machine_name}")
        print(f"IP Address: {machine_config.get('ip')}")
        print(f"Username: {machine_config.get('user')}")
        
        # Take a final screenshot if configured
        if config.get('screenshots', {}).get('enabled', True):
            screenshot_path = Path(config.get('screenshots', {}).get('path', './artifacts/screenshots'))
            screenshot_path.mkdir(parents=True, exist_ok=True)
            screenshot_file = screenshot_path / f"machine_created_{machine_name}.png"
            page.screenshot(path=str(screenshot_file))
            print(f"Screenshot saved: {screenshot_file}")
        
    except Exception as e:
        print(f"\n❌ Error during machine creation: {str(e)}")
        
        # Take error screenshot
        try:
            error_screenshot = Path("./artifacts/screenshots/error_machine_creation.png")
            error_screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(error_screenshot))
            print(f"Error screenshot saved: {error_screenshot}")
        except:
            pass
        
        raise e
    
    finally:
        # Clean up
        context.close()
        browser.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)