import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page1 = context.new_page()
    page1.goto("http://localhost:7322/console")
    time.sleep(2)  # Wait for page to load
    
    with page1.expect_popup() as page2_info:
        page1.get_by_role("banner").get_by_role("link", name="Login").click()
    page2 = page2_info.value
    time.sleep(1)  # Wait for login page
    
    page2.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page2.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    time.sleep(0.5)
    page2.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page2.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Pause before login
    page2.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    
    page2.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    time.sleep(1.5)  # Wait for resources page
    page2.get_by_test_id("machine-expand-rediacc11").click()
    time.sleep(1)  # Wait for machine to expand
    page2.get_by_test_id("machine-repo-list-table").get_by_role("img", name="right").locator("svg").click()
    time.sleep(1)  # Wait for repo to expand
    page2.get_by_test_id("machine-repo-list-container-actions-edbcc7482431").click()
    time.sleep(0.5)  # Wait for actions menu
    page2.get_by_text("container_inspect").click()
    time.sleep(2)  # Wait for inspection to complete

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
