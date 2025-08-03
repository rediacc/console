import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page24 = context.new_page()
    page24.goto("http://localhost:7322/en")
    time.sleep(2)
    with page24.expect_popup() as page25_info:
        page24.get_by_role("banner").get_by_role("link", name="Login").click()
    page25 = page25_info.value
    time.sleep(1)
    page25.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page25.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page25.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page25.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page25.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page25.get_by_text("System").click()
    time.sleep(1.5)
    page25.get_by_test_id("system-bridge-edit-button-testbridge01").click()
    time.sleep(1)
    page25.get_by_test_id("resource-modal-field-bridgeName-input").click()
    time.sleep(0.5)
    page25.get_by_test_id("resource-modal-field-bridgeName-input").fill("testbridge012")
    time.sleep(1)
    page25.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
