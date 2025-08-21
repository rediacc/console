import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page12 = context.new_page()
    page12.goto("http://localhost:7322/console")
    time.sleep(2)  # Wait for page to load
    with page12.expect_popup() as page13_info:
        page12.get_by_role("banner").get_by_role("link", name="Login").click()
    page13 = page13_info.value
    time.sleep(1)  # Wait for login page
    page13.get_by_test_id("login-email-input").click()
    page13.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page13.get_by_test_id("login-email-input").press("Tab")
    page13.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page13.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page13.get_by_test_id("main-mode-toggle").click()
    time.sleep(1)  # Wait for mode toggle

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
