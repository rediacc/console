import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page28 = context.new_page()
    page28.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page28.expect_popup() as page29_info:
        page28.get_by_test_id("banner-login-link").click()
    page29 = page29_info.value
    time.sleep(1)  # Wait for login page
    page29.get_by_test_id("login-email-input").click()
    page29.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page29.get_by_test_id("login-email-input").press("Tab")
    page29.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page29.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page29.get_by_test_id("main-nav-system").click()
    time.sleep(2)  # Wait for system page
    page29.get_by_test_id("system-tab-permissions").click()
    time.sleep(1)  # Wait for permissions tab
    page29.get_by_test_id("system-permission-group-delete-button-testgroup").click()
    time.sleep(1)  # Wait for confirmation
    page29.get_by_test_id("confirm-yes-button").click()
    time.sleep(2)  # Wait for deletion

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
