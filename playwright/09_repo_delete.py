import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page8 = context.new_page()
    page8.goto("http://localhost:7322/en")
    with page8.expect_popup() as page9_info:
        page8.get_by_role("banner").get_by_role("link", name="Login").click()
    page9 = page9_info.value
    page9.get_by_test_id("login-email-input").click()
    page9.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page9.get_by_test_id("login-email-input").press("Tab")
    page9.get_by_test_id("login-password-input").fill("admin")
    page9.get_by_test_id("login-password-input").press("Enter")
    page9.get_by_test_id("login-submit-button").click()
    page9.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    page9.get_by_test_id("resources-tab-repositories").click()
    page9.get_by_test_id("resources-repository-delete-a22").click()
    page9.get_by_role("button", name="Delete", exact=True).click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
