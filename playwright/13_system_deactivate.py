import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page16 = context.new_page()
    page16.goto("http://localhost:7322/en")
    with page16.expect_popup() as page17_info:
        page16.get_by_role("banner").get_by_role("link", name="Login").click()
    page17 = page17_info.value
    page17.get_by_test_id("login-email-input").click()
    page17.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page17.get_by_test_id("login-email-input").press("Tab")
    page17.get_by_test_id("login-password-input").fill("admin")
    page17.get_by_test_id("login-submit-button").click()
    page17.get_by_text("System").click()
    page17.get_by_test_id("system-user-deactivate-button-bridge.WGwAEwmU@1.local").click()
    page17.get_by_role("button", name="Yes").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
