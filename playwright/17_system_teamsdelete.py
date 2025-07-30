import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page26 = context.new_page()
    page26.goto("http://localhost:7322/en")
    with page26.expect_popup() as page27_info:
        page26.get_by_role("banner").get_by_role("link", name="Login").click()
    page27 = page27_info.value
    page27.get_by_test_id("login-email-input").click()
    page27.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page27.get_by_test_id("login-email-input").press("Tab")
    page27.get_by_test_id("login-password-input").fill("admin")
    page27.get_by_test_id("login-password-input").press("Tab")
    page27.get_by_test_id("login-submit-button").click()
    page27.get_by_text("System").click()
    page27.get_by_test_id("system-tab-teams").click()
    page27.get_by_test_id("system-team-delete-button-test2").click()
    page27.get_by_role("button", name="Yes").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
