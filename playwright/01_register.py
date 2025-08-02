import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page5 = context.new_page()
    page5.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page5.expect_popup() as page2_info:
        page5.get_by_role("banner").get_by_role("link", name="Login").click()
    page6 = page2_info.value
    time.sleep(1)  # Wait for popup to load
    # Click on French language option
    page6.get_by_text("🇫🇷 Français").click()
    time.sleep(0.5)
    page6.get_by_test_id("login-register-link").click()
    time.sleep(1)  # Wait for registration form
    page6.get_by_test_id("registration-company-input").click()
    page6.get_by_test_id("registration-company-input").fill("rediacc")
    page6.get_by_test_id("registration-company-input").press("Tab")
    page6.get_by_test_id("registration-email-input").fill("anil@rediacc.com")
    page6.get_by_test_id("registration-email-input").press("Tab")
    page6.get_by_test_id("registration-password-input").fill("87654321i_")
    page6.get_by_test_id("registration-password-input").press("Tab")
    page6.get_by_test_id("registration-password-confirm-input").fill("87654321i_")
    time.sleep(1)  # Wait before submit
    page6.get_by_test_id("registration-submit-button").click()
    time.sleep(2)  # Wait for registration to process
    page6.get_by_test_id("registration-activation-code-input").click()
    page6.get_by_test_id("registration-activation-code-input").fill("111111")
    time.sleep(1)  # Wait before verify
    page6.get_by_test_id("registration-verify-button").click()
    time.sleep(2)  # Wait for verification to complete

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
