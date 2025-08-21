import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page21 = context.new_page()
    page21.goto("http://localhost:7322/console")
    time.sleep(2)
    with page21.expect_popup() as page22_info:
        page21.get_by_role("banner").get_by_role("link", name="Login").click()
    page22 = page22_info.value
    time.sleep(1)
    page22.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page22.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page22.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page22.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page22.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page22.get_by_text("System").click()
    time.sleep(1.5)
    page22.get_by_test_id("system-create-bridge-button").click()
    time.sleep(1)
    page22.get_by_test_id("resource-modal-field-teamName-select").locator("div span").nth(2).click()
    time.sleep(0.5)
    page22.get_by_title("Private Team").locator("div").click()
    time.sleep(0.5)
    page22.get_by_test_id("resource-modal-field-bridgeName-input").click()
    time.sleep(0.5)
    page22.get_by_test_id("resource-modal-field-bridgeName-input").fill("testbridge01")
    time.sleep(1)
    page22.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
