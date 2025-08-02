from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page13 = context.new_page()
    page13.goto("http://localhost:7322/en")
    time.sleep(3)  # Wait for page to load
    
    with page13.expect_popup() as page14_info:
        page13.get_by_role("banner").get_by_role("link", name="Login").click()
    page14 = page14_info.value
    time.sleep(3)  # Wait for login page to fully load
    
    page14.get_by_test_id("login-email-input").click()
    time.sleep(1)  # Brief pause
    page14.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    time.sleep(1)  # Pause after entering email
    page14.get_by_test_id("login-email-input").press("Tab")
    time.sleep(1)  # Pause before password
    page14.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Pause after entering password
    page14.get_by_test_id("login-password-input").press("Enter")
    time.sleep(2)  # Wait before submit
    page14.get_by_test_id("login-submit-button").click()
    time.sleep(5)  # Wait for login to complete and dashboard to load
    page14.get_by_test_id("main-nav-resources").click()
    time.sleep(3)  # Wait for resources page to load
    
    page14.get_by_role("tab", name="cloud Storage").click()
    time.sleep(3)  # Wait for storage tab to load
    
    page14.get_by_role("button", name="Import").click()
    time.sleep(3)  # Wait for import dialog to open
    page14.get_by_test_id("rclone-wizard-upload-dragger").click()
    time.sleep(2)  # Wait for file dialog
    
    page14.get_by_test_id("rclone-wizard-upload-dragger").set_input_files("conf.conf")
    time.sleep(3)  # Wait for file to be processed
    
    page14.get_by_test_id("rclone-wizard-import-button").click()
    time.sleep(5)  # Wait for import operation to complete
    
    page14.get_by_test_id("rclone-wizard-close-button").click()
    time.sleep(2)  # Wait for dialog to close
    page14.get_by_test_id("main-nav-resources").click()
    time.sleep(3)  # Wait for machines page to load
    
    page14.get_by_test_id("machine-row-rediacc11").click()
    time.sleep(2)  # Wait for machine selection
    
    page14.get_by_test_id("machine-repositories-button-rediacc11").click()
    time.sleep(3)  # Wait for repositories to load
    
    page14.get_by_test_id("repo-action-push").click()
    time.sleep(3)  # Wait for push dialog to open
    page14.get_by_text("rediacc11 (Current Machine)").click()
    time.sleep(1)  # Wait for radio selection
    
    page14.get_by_test_id("push-target-machine-radio").click()
    time.sleep(1)  # Wait for target selection
    
    page14.get_by_test_id("push-storage-selector").click()
    time.sleep(2)  # Wait for storage selector to expand
    
    page14.get_by_test_id("push-storage-selection").click()
    time.sleep(2)  # Wait for storage options to appear
    
    page14.get_by_test_id("push-storage-option-microsoft").click()
    time.sleep(2)  # Wait for microsoft option selection
    
    page14.get_by_test_id("push-add-to-queue-button").click()
    time.sleep(5)  # Wait for queue operation to start
    
    page14.get_by_test_id("queue-trace-modal-close-button").click()
    time.sleep(2)  # Wait for modal to close

    # ---------------------
    time.sleep(2)  # Final pause before closing
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
