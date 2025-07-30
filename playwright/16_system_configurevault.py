import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page24 = context.new_page()
    page24.goto("http://localhost:7322/en")
    with page24.expect_popup() as page25_info:
        page24.get_by_role("banner").get_by_role("link", name="Login").click()
    page25 = page25_info.value
    page25.get_by_test_id("login-email-input").click()
    page25.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page25.get_by_test_id("login-email-input").press("Tab")
    page25.get_by_test_id("login-password-input").fill("admin")
    page25.get_by_test_id("login-submit-button").click()
    page25.get_by_text("System").click()
    page25.get_by_test_id("system-user-vault-button").click()
    page25.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY").click()
    page25.get_by_test_id("vault-editor-generate-button").click()
    page25.get_by_test_id("vault-editor-apply-generated").click()
    page25.get_by_test_id("vault-modal-save-button").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
