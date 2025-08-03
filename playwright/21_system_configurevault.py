import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page24 = context.new_page()
    page24.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page24.expect_popup() as page25_info:
        page24.get_by_role("banner").get_by_role("link", name="Login").click()
    page25 = page25_info.value
    time.sleep(1)  # Wait for login page
    page25.get_by_test_id("login-email-input").click()
    page25.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page25.get_by_test_id("login-email-input").press("Tab")
    page25.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page25.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page25.get_by_test_id("main-nav-system").click()
    time.sleep(2)  # Wait for system page
    page25.get_by_test_id("system-user-vault-button").click()
    time.sleep(1)  # Wait for vault dialog
    page25.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY").click()
    time.sleep(0.5)
    page25.get_by_test_id("vault-editor-generate-button").click()
    time.sleep(1)  # Wait for generation
    page25.get_by_test_id("vault-editor-apply-generated").click()
    time.sleep(0.5)
    page25.get_by_test_id("vault-modal-save-button").click()
    time.sleep(2)  # Wait for save

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
