import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page10 = context.new_page()
    page10.goto("http://localhost:7322/en")
    with page10.expect_popup() as page11_info:
        page10.get_by_role("banner").get_by_role("link", name="Login").click()
    page11 = page11_info.value
    page11.locator(".ant-input-affix-wrapper").first.click()
    page11.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page11.get_by_test_id("login-email-input").press("Tab")
    page11.get_by_test_id("login-password-input").fill("admin")
    page11.get_by_test_id("login-submit-button").click()
    page11.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    page11.get_by_test_id("machine-delete-rediacc11").click()
    page11.get_by_role("button", name="Delete", exact=True).click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
