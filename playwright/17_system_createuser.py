import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page14 = context.new_page()
    page14.goto("http://localhost:7322/console")
    time.sleep(2)  # Wait for page to load
    with page14.expect_popup() as page15_info:
        page14.get_by_role("banner").get_by_role("link", name="Login").click()
    page15 = page15_info.value
    time.sleep(1)  # Wait for login page
    page15.get_by_test_id("login-email-input").click()
    page15.get_by_test_id("login-email-input").fill("admin@rediacc.ioı")
    page15.get_by_test_id("login-email-input").press("Tab")
    page15.get_by_test_id("login-email-input").click()
    page15.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page15.get_by_test_id("login-email-input").press("Tab")
    page15.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page15.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page15.get_by_test_id("main-nav-system").click()
    time.sleep(2)  # Wait for system page
    page15.get_by_test_id("system-create-user-button").click()
    time.sleep(1)  # Wait for create user dialog
    page15.get_by_test_id("create-user-email-input").click()
    page15.get_by_test_id("create-user-email-input").fill("contact@rediacc.com")
    page15.get_by_test_id("create-user-email-input").press("Tab")
    page15.get_by_test_id("create-user-password-input").fill("contact12345678")
    time.sleep(1)  # Wait before submit
    page15.get_by_test_id("create-user-submit-button").click()
    time.sleep(2)  # Wait for user creation

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
