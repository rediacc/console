import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page4 = context.new_page()
    page4.goto("http://localhost:7322/en")
    with page4.expect_popup() as page5_info:
        page4.get_by_role("banner").get_by_role("link", name="Login").click()
    page5 = page5_info.value
    page5.get_by_test_id("login-email-input").click()
    page5.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page5.get_by_test_id("login-email-input").press("Tab")
    page5.get_by_test_id("login-password-input").fill("admin")
    page5.get_by_test_id("login-password-input").press("Enter")
    page5.get_by_test_id("login-submit-button").click()
    page5.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    page5.get_by_test_id("machine-trace-rediacc11").click()
    page5.get_by_text("Updated", exact=True).click()
    page5.get_by_text("Created").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
