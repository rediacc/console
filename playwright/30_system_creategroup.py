import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page34 = context.new_page()
    page34.goto("http://localhost:7322/en")
    time.sleep(2)
    with page34.expect_popup() as page35_info:
        page34.get_by_role("banner").get_by_role("link", name="Login").click()
    page35 = page35_info.value
    time.sleep(1)
    page35.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page35.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page35.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page35.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page35.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page35.get_by_text("System").click()
    time.sleep(1.5)
    page35.get_by_test_id("system-tab-permissions").click()
    time.sleep(1)
    page35.get_by_test_id("system-create-permission-group-button").click()
    time.sleep(1)
    page35.get_by_test_id("system-permission-group-name-input").click()
    time.sleep(0.5)
    page35.get_by_test_id("system-permission-group-name-input").fill("grup01")
    time.sleep(1)
    page35.get_by_test_id("modal-create-permission-group-ok").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
