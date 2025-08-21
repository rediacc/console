import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page7 = context.new_page()
    page7.goto("http://localhost:7322/console")
    time.sleep(2)  # Wait for page to load
    
    with page7.expect_popup() as page8_info:
        page7.get_by_role("banner").get_by_role("link", name="Login").click()
    page8 = page8_info.value
    time.sleep(1)  # Wait for login page
    
    page8.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page8.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    time.sleep(0.5)
    page8.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page8.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Pause before login
    page8.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    
    page8.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    time.sleep(1.5)  # Wait for resources page
    page8.get_by_test_id("machine-expand-rediacc11").locator("svg").click()
    time.sleep(1)  # Wait for machine to expand
    page8.get_by_test_id("machine-repo-list-table").get_by_role("cell", name="right inbox repo006").locator("span").first.click()
    time.sleep(1)  # Wait for repo to expand
    page8.get_by_test_id("machine-repo-list-container-actions-edbcc7482431").click()
    time.sleep(0.5)  # Wait for actions menu
    page8.get_by_text("container_logs").click()
    time.sleep(2)  # Wait for logs to load

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
