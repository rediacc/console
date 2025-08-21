import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page26 = context.new_page()
    page26.goto("http://localhost:7322/console")
    time.sleep(2)  # Wait for page to load
    with page26.expect_popup() as page27_info:
        page26.get_by_role("banner").get_by_role("link", name="Login").click()
    page27 = page27_info.value
    time.sleep(1)  # Wait for login page
    page27.get_by_test_id("login-email-input").click()
    page27.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page27.get_by_test_id("login-email-input").press("Tab")
    page27.get_by_test_id("login-password-input").fill("admin")
    page27.get_by_test_id("login-password-input").press("Tab")
    time.sleep(1)  # Wait before submit
    page27.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page27.get_by_test_id("main-nav-system").click()
    time.sleep(2)  # Wait for system page
    page27.get_by_test_id("system-tab-teams").click()
    time.sleep(1)  # Wait for teams tab
    page27.get_by_test_id("system-team-delete-button-test2").click()
    time.sleep(1)  # Wait for confirmation
    page27.get_by_test_id("confirm-yes-button").click()
    time.sleep(2)  # Wait for deletion

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
