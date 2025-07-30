import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page16 = context.new_page()
    page16.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page16.expect_popup() as page17_info:
        page16.get_by_test_id("banner-login-link").click()
    page17 = page17_info.value
    time.sleep(1)  # Wait for login page
    page17.get_by_test_id("login-email-input").click()
    page17.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page17.get_by_test_id("login-email-input").press("Tab")
    page17.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page17.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page17.get_by_test_id("main-nav-system").click()
    time.sleep(2)  # Wait for system page
    page17.get_by_test_id("system-user-deactivate-button-bridge.WGwAEwmU@1.local").click()
    time.sleep(1)  # Wait for confirmation dialog
    page17.get_by_test_id("confirm-yes-button").click()
    time.sleep(2)  # Wait for deactivation

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
