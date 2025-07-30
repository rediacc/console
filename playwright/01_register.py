import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page5 = context.new_page()
    page5.goto("http://localhost:7322/en")
    with page5.expect_popup() as page2_info:
        page5.get_by_role("banner").get_by_role("link", name="Login").click()
    page6 = page2_info.value
    page6.locator("span").filter(has_text="🇬🇧 English").nth(1).click()
    page6.get_by_text("🇫🇷 Français").click()
    page6.get_by_test_id("login-register-link").click()
    page6.get_by_test_id("registration-company-input").click()
    page6.get_by_test_id("registration-company-input").fill("rediacc")
    page6.get_by_test_id("registration-company-input").press("Tab")
    page6.get_by_test_id("registration-email-input").fill("anil@rediacc.comm")
    page6.get_by_test_id("registration-email-input").press("Tab")
    page6.get_by_test_id("registration-password-input").fill("rediacc87654321")
    page6.get_by_test_id("registration-password-input").press("Tab")
    page6.get_by_test_id("registration-password-confirm-input").fill("rediacc87654321")
    page6.get_by_test_id("registration-submit-button").click()
    page6.get_by_test_id("registration-activation-code-input").click()
    page6.get_by_test_id("registration-activation-code-input").fill("111111")
    page6.get_by_test_id("registration-verify-button").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
