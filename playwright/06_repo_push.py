import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page1 = context.new_page()
    page1.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    
    with page1.expect_popup() as page2_info:
        page1.get_by_role("banner").get_by_role("link", name="Login").click()
    page2 = page2_info.value
    time.sleep(2)  # Wait for login page to fully load
    
    page2.get_by_test_id("login-email-input").click()
    time.sleep(0.5)  # Brief pause
    page2.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    time.sleep(0.5)  # Pause after entering email
    page2.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)  # Pause before password
    page2.get_by_test_id("login-password-input").fill("admin")
    time.sleep(0.5)  # Pause after entering password
    page2.get_by_test_id("login-submit-button").click()
    time.sleep(3)  # Wait for login to complete and dashboard to load
    page2.get_by_test_id("main-nav-resources").click()
    time.sleep(3)  # Wait for resources page to fully load
    
    page2.get_by_test_id("machine-remote-rediacc11").click()
    time.sleep(2)  # Wait for machine expansion and repositories to load
    
    page2.get_by_test_id("machine-repo-list-repo-actions-Repo001").click()
    time.sleep(1)  # Wait for menu to appear
    
    page2.get_by_text("push").click()
    time.sleep(2)  # Wait for push dialog to open
    page2.get_by_text("rediacc11 (Current Machine)").click()
    time.sleep(1)  # Wait for selection
    
    page2.get_by_title("rediacc12").locator("div").click()
    time.sleep(1)  # Wait for target selection
    
    page2.get_by_test_id("function-modal-submit").click()
    time.sleep(3)  # Wait for push operation to start and queue trace to appear
    
    page2.get_by_test_id("queue-trace-close-button").click()
    time.sleep(1)  # Wait for dialog to close

    # ---------------------
    time.sleep(2)  # Final pause before closing
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
