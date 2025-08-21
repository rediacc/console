import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page38 = context.new_page()
    page38.goto("http://localhost:7322/console")
    with page38.expect_popup() as page39_info:
        page38.get_by_role("banner").get_by_role("link", name="Login").click()
    page39 = page39_info.value
    page39.get_by_test_id("login-email-input").click()
    page39.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page39.get_by_test_id("login-email-input").press("Tab")
    page39.get_by_test_id("login-password-input").fill("admin")
    page39.get_by_test_id("login-submit-button").click()
    page39.get_by_text("System").click()
    page39.get_by_test_id("system-region-delete-button-region004").click()
    page39.get_by_role("button", name="Yes").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
