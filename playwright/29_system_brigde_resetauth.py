import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page26 = context.new_page()
    page26.goto("http://localhost:7322/console")
    time.sleep(2)
    with page26.expect_popup() as page27_info:
        page26.get_by_role("banner").get_by_role("link", name="Login").click()
    page27 = page27_info.value
    time.sleep(1)
    page27.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page27.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page27.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page27.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page27.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page27.get_by_text("System").click()
    time.sleep(1.5)
    page27.get_by_test_id("system-bridge-reset-auth-button-testbridge012").click()
    time.sleep(1)
    page27.get_by_role("button", name="Reset Authorization").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
