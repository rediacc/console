#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# Add parent directory to path for test_utils import
sys.path.append(str(Path(__file__).parent.parent))

from logging_utils import StructuredLogger


def load_config(config_path="config.json"):
    """Load configuration from JSON file"""
    possible_paths = [
        Path(config_path),
        Path(__file__).parent / config_path,
        Path(__file__).parent.parent / config_path,  # Parent directory (playwright)
        Path.cwd() / config_path,
    ]
    
    for path in possible_paths:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    raise FileNotFoundError(
        f"Configuration file not found. Tried locations:\n" + 
        "\n".join(f"  - {p}" for p in possible_paths)
    )




def create_repository(page, config):
    """Create a new repository"""
    # No need to navigate - we should already be logged in
    # Just navigate to Resources using the menu
    repo_config = config["createRepo"]
    timeouts = repo_config["timeouts"]
    
    # Navigate to resources page
    print("📂 Navigating to Resources page...")
    resources_nav = page.get_by_test_id("main-nav-resources")
    resources_nav.wait_for(state="visible", timeout=timeouts["element"])
    resources_nav.click()
    
    # Wait for resources page to load
    page.wait_for_url("**/console/resources", timeout=timeouts["navigation"])
    page.wait_for_load_state("networkidle")
    
    # Click on the machine's remote button
    machine_name = repo_config["machineName"]
    print(f"🖥️  Selecting machine: {machine_name}")
    
    machine_remote = page.get_by_test_id(f"machine-remote-{machine_name}")
    machine_remote.wait_for(state="visible", timeout=timeouts["element"])
    machine_remote.click()
    
    # Wait for context menu and click Create Repo
    print("📝 Opening Create Repo dialog...")
    create_repo_menu = page.get_by_text("Create Repo")
    create_repo_menu.wait_for(state="visible", timeout=timeouts["modalOpen"])
    create_repo_menu.click()
    
    # Wait for modal to open
    page.wait_for_selector('[role="dialog"]', state="visible", timeout=timeouts["modalOpen"])
    
    # Use session repository name (generated once per test session)
    # This will be consistent across all tests in a session
    from test_utils import TestBase
    repo_name = TestBase._session_repository_name
    if not repo_name:
        # Fallback if somehow not initialized
        repo_name = TestBase.generate_session_repository_name()
        TestBase._session_repository_name = repo_name
    print(f"📝 Repository name: {repo_name}")
    
    repo_name_input = page.get_by_test_id("resource-modal-field-repositoryName-input")
    repo_name_input.wait_for(state="visible", timeout=timeouts["element"])
    repo_name_input.fill(repo_name)
    
    # Fill repository size
    repo_size = repo_config["repositorySize"]
    print(f"💾 Repository size: {repo_size}G")
    
    size_input = page.get_by_test_id("resource-modal-field-size-size-input")
    size_input.wait_for(state="visible", timeout=timeouts["element"])
    size_input.clear()
    size_input.fill(repo_size)
    
    # Select template
    template = repo_config["template"]
    if template and template != "none":
        print(f"📦 Selecting template: {template}")
        
        # Click to expand template selector
        template_button = page.get_by_role("button", name="collapsed appstore Select")
        template_button.wait_for(state="visible", timeout=timeouts["element"])
        template_button.click()
        
        # Wait for template list to be visible
        page.wait_for_selector('.ant-card', state="visible", timeout=timeouts["element"])
        
        # Select the template
        if template.lower() == "nginx":
            # Click on Nginx template
            nginx_template = page.locator('text=NginxMinimal Nginx web server')
            nginx_template.wait_for(state="visible", timeout=timeouts["element"])
            nginx_template.click()
        else:
            # Generic template selection
            template_selector = page.locator(f'text={template}').first
            template_selector.wait_for(state="visible", timeout=timeouts["element"])
            template_selector.click()
        
        # Collapse template selector
        template_button_expanded = page.get_by_role("button", name="expanded appstore Select")
        template_button_expanded.wait_for(state="visible", timeout=timeouts["element"])
        template_button_expanded.click()
    
    # Generate password if configured
    if repo_config["generatePassword"]:
        print("🔑 Generating random password...")
        
        # Click on password generation icon
        password_gen_icon = page.get_by_test_id("vault-editor-generate-credential")
        password_gen_icon.wait_for(state="visible", timeout=timeouts["element"])
        password_gen_icon.click()
        
        # Wait for popup and click Generate
        generate_button = page.get_by_test_id("vault-editor-generate-button")
        generate_button.wait_for(state="visible", timeout=timeouts["element"])
        generate_button.click()
        
        # Wait for generation success
        page.wait_for_selector('text=Generated successfully', state="visible", timeout=timeouts["element"])
        
        # Apply the generated password
        apply_button = page.get_by_test_id("vault-editor-apply-generated")
        apply_button.wait_for(state="visible", timeout=timeouts["element"])
        apply_button.click()
        
        # Wait for apply success
        page.wait_for_selector('text=Values applied successfully', state="visible", timeout=timeouts["element"])
    
    # Click Create button
    print("🚀 Creating repository...")
    create_button = page.get_by_test_id("resource-modal-ok-button")
    create_button.wait_for(state="visible", timeout=timeouts["element"])
    create_button.click()
    
    # Wait for Queue Item Trace dialog to appear
    print("⏳ Waiting for Queue Item Trace dialog...")
    queue_timeout = repo_config.get("queueTimeout", 120000)  # Default 120 seconds
    
    try:
        # Wait for the Queue Item Trace dialog to appear
        page.wait_for_selector('[role="dialog"]:has-text("Queue Item Trace")', 
                               state="visible", 
                               timeout=queue_timeout)
        print("📊 Queue Item Trace dialog opened")
        
        # Wait for task completion
        print("⏳ Waiting for task completion...")
        
        # Wait for the success alert with "Task Completed Successfully" 
        # and "The task finished successfully after X seconds"
        success_found = False
        
        try:
            # Look for the success alert box specifically
            success_alert = page.wait_for_selector(
                '.ant-alert-success:has-text("Task Completed Successfully")', 
                state="visible", 
                timeout=queue_timeout
            )
            
            if success_alert:
                print("✅ Task Completed Successfully")
                
                # Try to get the duration message
                try:
                    duration_text = page.locator('.ant-alert-success:has-text("The task finished successfully after")').text_content()
                    if duration_text and "after" in duration_text:
                        # Extract duration from text like "The task finished successfully after 36 seconds."
                        print(f"📝 {duration_text.strip()}")
                except:
                    pass
                
                success_found = True
        except:
            # Fallback: Check for completed status in the steps
            try:
                completed_step = page.wait_for_selector(
                    'text=/Completed.*Done/', 
                    state="visible", 
                    timeout=5000
                )
                if completed_step:
                    print("✅ Task completed (Step 4: Completed)")
                    success_found = True
            except:
                pass
        
        if success_found:
            # Optional: Check duration and machine info
            try:
                duration = page.locator('text=/Duration/:has(strong)').locator('strong').text_content()
                if duration:
                    print(f"⏱️  Duration: {duration}")
            except:
                pass
            
            # Wait a bit to ensure everything is loaded
            page.wait_for_timeout(2000)
            
            # Always close Queue Item Trace dialog for shared session tests
            try:
                close_button = page.locator('button:has-text("Close")').last
                close_button.wait_for(state="visible", timeout=timeouts["element"])
                close_button.click()
                print("📊 Closed Queue Item Trace dialog")
            except:
                print("⚠️  Could not find Close button for Queue Item Trace dialog")
        else:
            print("⚠️  Repository creation completed but success message not found")
            
    except Exception as e:
        print(f"⚠️  Queue Item Trace dialog did not appear or timed out: {e}")
    
    return repo_name


def run_with_page(page, config: dict) -> str:
    """Run the repository creation with existing page/session"""
    # Create logger for this test run
    logger = StructuredLogger("createrepo", config=config.get('logging', {}))
    logger.log_test_start("CreateRepositoryTest")
    
    screenshots = config.get("screenshots", {})
    test_start_time = time.time()
    repo_name = None  # Initialize repo_name to avoid UnboundLocalError
    
    try:
        # Create repository
        repo_name = create_repository(page, config)
        
        print(f"✅ Repository '{repo_name}' created successfully!")
        logger.info("Repository created successfully", repo_name=repo_name)
        
        # Take success screenshot if enabled
        if screenshots.get("enabled", False) and not page.is_closed():
            try:
                screenshot_dir = Path(screenshots.get("path", "./screenshots"))
                screenshot_dir.mkdir(exist_ok=True, parents=True)
                success_path = screenshot_dir / f"createrepo_success_{repo_name}.png"
                page.screenshot(path=str(success_path))
                print(f"📸 Screenshot saved as {success_path}")
                logger.info("Success screenshot captured", path=str(success_path))
            except Exception as e:
                print("⚠️  Could not take success screenshot - page may be closed")
                logger.warning("Failed to capture success screenshot", error=str(e))
        
        test_duration_ms = (time.time() - test_start_time) * 1000
        logger.log_test_end("CreateRepositoryTest", success=True, duration_ms=test_duration_ms)
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        test_duration_ms = (time.time() - test_start_time) * 1000
        logger.error("Repository creation failed", error=e, duration_ms=test_duration_ms)
        
        # Take failure screenshot if enabled
        if screenshots.get("enabled", False) and not page.is_closed():
            try:
                screenshot_dir = Path(screenshots.get("path", "./screenshots"))
                screenshot_dir.mkdir(exist_ok=True, parents=True)
                failure_path = screenshot_dir / f"createrepo_failed_{int(time.time())}.png"
                page.screenshot(path=str(failure_path))
                print(f"📸 Error screenshot saved as {failure_path}")
                logger.info("Error screenshot captured", path=str(failure_path))
            except Exception as screenshot_error:
                print("⚠️  Could not take error screenshot - page may be closed")
                logger.warning("Failed to capture error screenshot", error=str(screenshot_error))
        
        logger.log_test_end("CreateRepositoryTest", success=False, duration_ms=test_duration_ms)
        raise
    
    finally:
        # Return the created repository name
        return repo_name


def run(playwright: Playwright, config: dict) -> None:
    """Run the repository creation automation (standalone mode)"""
    browser_config = config["browser"]
    screenshots = config.get("screenshots", {})
    
    browser = playwright.chromium.launch(
        headless=browser_config["headless"],
        slow_mo=browser_config["slowMo"]
    )
    context = browser.new_context()
    page = context.new_page()
    
    try:
        # Login first
        base_url = config["baseUrl"]
        login_config = config["login"]
        credentials = login_config["credentials"]
        timeouts = login_config["timeouts"]
        
        login_url = f"{base_url}/console/login"
        print(f"📍 Navigating to: {login_url}")
        page.goto(login_url, wait_until="networkidle")
        
        email = credentials["email"]
        password = credentials["password"]
        
        print(f"👤 Logging in as: {email}")
        
        # Fill login form
        email_input = page.get_by_test_id("login-email-input")
        email_input.wait_for(state="visible", timeout=timeouts["element"])
        email_input.fill(email)
        
        password_input = page.get_by_test_id("login-password-input")
        password_input.fill(password)
        
        # Submit form
        submit_button = page.get_by_test_id("login-submit-button")
        submit_button.click()
        
        # Wait for dashboard
        dashboard_url = config["validation"]["dashboardUrl"]
        page.wait_for_url(dashboard_url, timeout=timeouts["navigation"])
        print("✅ Login successful!")
        
        # Create repository
        repo_name = create_repository(page, config)
        
        print(f"✅ Repository '{repo_name}' created successfully!")
        
        # Take success screenshot if enabled
        if screenshots.get("enabled", False):
            screenshot_dir = Path(screenshots.get("path", "./screenshots"))
            screenshot_dir.mkdir(exist_ok=True, parents=True)
            success_path = screenshot_dir / f"createrepo_success_{repo_name}.png"
            page.screenshot(path=str(success_path))
            print(f"📸 Screenshot saved as {success_path}")
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        
        # Take failure screenshot if enabled
        if screenshots.get("enabled", False):
            screenshot_dir = Path(screenshots.get("path", "./screenshots"))
            screenshot_dir.mkdir(exist_ok=True, parents=True)
            failure_path = screenshot_dir / f"createrepo_failed_{int(time.time())}.png"
            page.screenshot(path=str(failure_path))
            print(f"📸 Error screenshot saved as {failure_path}")
        
        raise
    
    finally:
        # Wait a bit before closing to see the result
        page.wait_for_timeout(2000)
        context.close()
        browser.close()


def main():
    """Main entry point"""
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