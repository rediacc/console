import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page43 = context.new_page()
    page43.goto("http://localhost:7322/en")
    time.sleep(2)
    with page43.expect_popup() as page44_info:
        page43.get_by_role("banner").get_by_role("link", name="Login").click()
    page44 = page44_info.value
    time.sleep(1)
    page44.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page44.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page44.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page44.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page44.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page44.get_by_text("System").click()
    time.sleep(1.5)
    page44.get_by_test_id("system-region-edit-button-test001").click()
    time.sleep(1)
    page44.get_by_test_id("resource-modal-field-regionName-input").click()
    time.sleep(0.5)
    page44.get_by_test_id("resource-modal-field-regionName-input").fill("test002")
    time.sleep(1)
    page44.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
