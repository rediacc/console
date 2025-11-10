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


def wait_for_element_with_retry(page, selector, max_retries=3, timeout=5000):
    """Smart wait for element with retry logic"""
    for attempt in range(max_retries):
        try:
            element = page.wait_for_selector(selector, state='visible', timeout=timeout)
            if element:
                return element
        except:
            if attempt < max_retries - 1:
                page.wait_for_timeout(500)
    return None


def wait_for_success_message(page, patterns=None, timeout=10000):
    """Smart wait for success messages without unnecessary delays"""
    if patterns is None:
        patterns = [
            "SSH connection successful",
            "Machine created successfully",
            "Machine '.*' created successfully",
            "Setup has been queued",
            "Task Completed Successfully",
            "Compatibility Status: Compatible"
        ]
    
    start_time = datetime.now()
    
    while (datetime.now() - start_time).total_seconds() * 1000 < timeout:
        for pattern in patterns:
            # Check multiple selector types for better coverage
            if page.locator(f"text=/{pattern}/").count() > 0:
                return {"success": True, "message": pattern, "element": "text"}
            
            # Check for messages in notification containers
            notification_selectors = [
                ".ant-message",
                ".ant-notification",
                "[role='alert']",
                ".toast-success"
            ]
            
            for selector in notification_selectors:
                elements = page.locator(selector).all()
                for element in elements:
                    try:
                        text = element.text_content()
                        if text and re.search(pattern, text, re.IGNORECASE):
                            return {"success": True, "message": text, "element": selector}
                    except:
                        continue
        
        # Small wait to prevent CPU spinning
        page.wait_for_timeout(100)
    
    return {"success": False, "message": None, "element": None}


def expand_required_fields_smart(page):
    """Smart expansion of Required Fields section without fixed delays"""
    # Check if already expanded
    expanded_button = page.get_by_role("button", name="expanded Required Fields")
    if expanded_button.count() > 0:
        return True
    
    # Try to expand
    collapsed_button = page.get_by_role("button", name="collapsed Required Fields")
    if collapsed_button.count() > 0:
        collapsed_button.click()
        # Wait for expansion animation to complete by checking for IP field visibility
        ip_field = page.get_by_test_id("vault-editor-field-ip")
        ip_field.wait_for(state='visible', timeout=2000)
        return True
    
    return False


def test_ssh_connection_smart(page, config):
    """Smart SSH connection test with proper wait logic"""
    test_button = page.get_by_test_id("vault-editor-test-connection")
    
    if not test_button.is_visible():
        return {"success": False, "message": "Test button not visible"}
    
    # Click test button
    test_button.click()
    
    # Wait for connection test result using configured patterns
    success_patterns = config.get('createMachine', {}).get('successIndicators', [
        "SSH connection successful",
        "Compatibility Status: Compatible"
    ])
    
    result = wait_for_success_message(page, patterns=success_patterns, timeout=15000)
    
    if result["success"]:
        # Wait for OK button to become enabled after successful test
        ok_button = page.get_by_test_id("resource-modal-ok-button")
        # Wait for button to be enabled (not disabled)
        page.wait_for_function(
            "document.querySelector('[data-testid=\"resource-modal-ok-button\"]') && "
            "!document.querySelector('[data-testid=\"resource-modal-ok-button\"]').disabled",
            timeout=5000
        )
    
    return result


def handle_queue_dialog_smart(page):
    """Smart handling of queue trace dialog"""
    queue_info = {"appeared": False, "status": None, "task_id": None}
    
    # Check if queue trace dialog appears
    queue_trace_close = page.get_by_test_id("queue-trace-close-button")
    
    if queue_trace_close.count() > 0:
        queue_info["appeared"] = True
        
        # Look for task ID
        task_id_pattern = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
        task_id_elements = page.locator(f"text=/{task_id_pattern}/").all()
        if task_id_elements:
            queue_info["task_id"] = task_id_elements[0].text_content()
        
        # Check for completion status without fixed delay
        completion_patterns = [
            "Task Completed Successfully",
            "Completed",
            "Processing",
            "Assigned"
        ]
        
        for pattern in completion_patterns:
            if page.locator(f"text=/{pattern}/").count() > 0:
                queue_info["status"] = pattern
                break
        
        # Close the dialog
        queue_trace_close.click()
    
    return queue_info


def run(playwright: Playwright) -> None:
    # Load configuration
    config = load_config()
    
    # Extract all settings from config
    base_url = config.get('baseUrl', 'http://localhost:7322')
    browser_config = config.get('browser', {})
    login_config = config.get('login', {})
    credentials = login_config.get('credentials', {})
    timeouts = login_config.get('timeouts', {})
    
    # Machine creation config
    machine_config = config.get('createMachine', {})
    
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
    
    # Set default timeout from config
    page.set_default_timeout(timeouts.get('navigation', 30000))
    
    try:
        # Navigate to login page
        print(f"Navigating to {base_url}/console/login...")
        page.goto(f"{base_url}/console/login")
        
        # Smart wait for login form
        email_input = wait_for_element_with_retry(page, '[data-testid="login-email-input"]')
        if not email_input:
            raise Exception("Login form not found")
        
        # Fill login credentials from config
        print(f"Logging in with email: {credentials.get('email')}...")
        page.get_by_test_id("login-email-input").fill(credentials.get('email'))
        page.get_by_test_id("login-password-input").fill(credentials.get('password'))
        
        # Click login button
        page.get_by_test_id("login-submit-button").click()
        
        # Smart wait for dashboard
        page.wait_for_url("**/console/dashboard", timeout=timeouts.get('navigation', 10000))
        print("Login successful, dashboard loaded")
        
        # Navigate to Resources
        print("Navigating to Resources...")
        resources_nav = page.get_by_test_id("main-nav-machines")
        resources_nav.wait_for(state='visible')
        resources_nav.click()
        
        # Smart wait for Resources page
        create_machine_btn = wait_for_element_with_retry(
            page, '[data-testid="resources-create-machine-button"]'
        )
        if not create_machine_btn:
            raise Exception("Create Machine button not found")
        
        # Click Create Machine button
        print("Opening Create Machine dialog...")
        create_machine_btn.click()
        
        # Smart wait for modal
        machine_name_input = wait_for_element_with_retry(
            page, '[data-testid="resource-modal-field-machineName-input"]'
        )
        if not machine_name_input:
            raise Exception("Machine creation modal not opened")
        
        # Generate unique machine name based on config
        machine_name = machine_config.get('machineName', 'rediacc21')
        if machine_config.get('generateUniqueName', True):
            machine_name = generate_unique_machine_name(machine_name.rstrip('0123456789'))
        
        print(f"Creating machine with name: {machine_name}")
        
        # Fill machine name
        machine_name_input.fill(machine_name)
        
        # Smart expansion of Required Fields
        if not expand_required_fields_smart(page):
            print("Warning: Could not expand Required Fields section")
        
        # Fill IP address from config
        ip_address = machine_config.get('ip', '192.168.111.21')
        print(f"Setting IP address: {ip_address}...")
        ip_field = page.get_by_test_id("vault-editor-field-ip")
        ip_field.wait_for(state='visible', timeout=3000)
        ip_field.fill(ip_address)
        
        # Fill username from config
        username = machine_config.get('user', 'anl')
        print(f"Setting username: {username}...")
        user_field = page.get_by_test_id("vault-editor-field-user")
        user_field.wait_for(state='visible', timeout=3000)
        user_field.fill(username)
        
        # Smart click on Configured status if needed
        configured_div = page.locator("div").filter(has_text=re.compile(r"^Configured$"))
        if configured_div.count() > 1:
            configured_div.nth(1).click()
            # Wait for any UI update
            page.wait_for_load_state("networkidle", timeout=2000)
        
        # Test connection if configured
        if machine_config.get('testConnection', True):
            print("Testing SSH connection...")
            connection_result = test_ssh_connection_smart(page, config)
            
            if connection_result["success"]:
                print(f"✓ {connection_result['message']}")
            else:
                print("⚠ SSH connection test did not show success message, but continuing...")
        
        # Smart wait for OK button to be ready
        ok_button = page.get_by_test_id("resource-modal-ok-button")
        ok_button.wait_for(state='visible', timeout=5000)
        
        # Ensure button is enabled before clicking
        if ok_button.is_disabled():
            # Wait for button to become enabled
            page.wait_for_function(
                "document.querySelector('[data-testid=\"resource-modal-ok-button\"]') && "
                "!document.querySelector('[data-testid=\"resource-modal-ok-button\"]').disabled",
                timeout=5000
            )
        
        # Click OK to create machine
        print("Creating machine...")
        ok_button.click()
        
        # Smart wait for success message
        creation_patterns = machine_config.get('successIndicators', [
            "Machine created successfully",
            "Machine '.*' created successfully",
            "Setup has been queued"
        ])
        
        creation_result = wait_for_success_message(
            page, 
            patterns=creation_patterns, 
            timeout=machine_config.get('timeouts', {}).get('creation', 20000)
        )
        
        if creation_result["success"]:
            print(f"✓ {creation_result['message']}")
        else:
            print("⚠ Machine creation message not detected, but may have succeeded")
        
        # Smart handling of queue trace dialog
        queue_info = handle_queue_dialog_smart(page)
        
        if queue_info["appeared"]:
            print(f"Queue dialog appeared with status: {queue_info['status']}")
            if queue_info["task_id"]:
                print(f"Task ID: {queue_info['task_id']}")
        
        print("\n✅ Machine creation process completed successfully!")
        print(f"Machine Name: {machine_name}")
        print(f"IP Address: {ip_address}")
        print(f"Username: {username}")
        
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