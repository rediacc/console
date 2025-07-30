import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page12 = context.new_page()
    page12.goto("http://localhost:7322/en")
    with page12.expect_popup() as page13_info:
        page12.get_by_test_id("banner-login-link").click()
    page13 = page13_info.value
    page13.get_by_test_id("login-email-input").click()
    page13.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page13.get_by_test_id("login-email-input").press("Tab")
    page13.get_by_test_id("login-password-input").fill("admin")
    page13.get_by_test_id("login-submit-button").click()
    page13.get_by_test_id("main-mode-toggle").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
