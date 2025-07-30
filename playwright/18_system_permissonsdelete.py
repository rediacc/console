import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page28 = context.new_page()
    page28.goto("http://localhost:7322/en")
    with page28.expect_popup() as page29_info:
        page28.get_by_role("banner").get_by_role("link", name="Login").click()
    page29 = page29_info.value
    page29.get_by_test_id("login-email-input").click()
    page29.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page29.get_by_test_id("login-email-input").press("Tab")
    page29.get_by_test_id("login-password-input").fill("admin")
    page29.get_by_test_id("login-submit-button").click()
    page29.get_by_text("System").click()
    page29.get_by_test_id("system-tab-permissions").click()
    page29.get_by_test_id("system-permission-group-delete-button-testgroup").click()
    page29.get_by_role("button", name="Yes").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
