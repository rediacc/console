import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page14 = context.new_page()
    page14.goto("http://localhost:7322/en")
    with page14.expect_popup() as page15_info:
        page14.get_by_role("banner").get_by_role("link", name="Login").click()
    page15 = page15_info.value
    page15.get_by_test_id("login-email-input").click()
    page15.get_by_test_id("login-email-input").fill("admin@rediacc.ioı")
    page15.get_by_test_id("login-email-input").press("Tab")
    page15.get_by_test_id("login-email-input").click()
    page15.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page15.get_by_test_id("login-email-input").press("Tab")
    page15.get_by_test_id("login-password-input").fill("admin")
    page15.get_by_test_id("login-submit-button").click()
    page15.get_by_text("System").click()
    page15.get_by_test_id("system-create-user-button").click()
    page15.get_by_role("textbox", name="user@example.com").click()
    page15.get_by_role("textbox", name="user@example.com").fill("contact@rediacc.com")
    page15.get_by_role("textbox", name="user@example.com").press("Tab")
    page15.get_by_role("textbox", name="Enter password").fill("contact12345678")
    page15.get_by_role("button", name="Create", exact=True).click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
