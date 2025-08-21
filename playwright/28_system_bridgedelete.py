import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page32 = context.new_page()
    page32.goto("http://localhost:7322/console")
    time.sleep(2)
    with page32.expect_popup() as page33_info:
        page32.get_by_role("banner").get_by_role("link", name="Login").click()
    page33 = page33_info.value
    time.sleep(1)
    page33.locator(".ant-input-affix-wrapper").first.click()
    time.sleep(0.5)
    page33.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page33.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page33.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page33.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page33.get_by_text("System").click()
    time.sleep(1.5)
    page33.get_by_test_id("system-bridge-delete-button-testbridge012").click()
    time.sleep(1)
    page33.get_by_role("button", name="Yes").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
