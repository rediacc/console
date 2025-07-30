from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page9 = context.new_page()
    page9.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page9.expect_popup() as page10_info:
        page9.get_by_test_id("banner-login-link").click()
    page10 = page10_info.value
    time.sleep(1)  # Wait for login page
    page10.get_by_test_id("login-email-input").click()
    page10.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page10.get_by_test_id("login-email-input").press("Tab")
    page10.get_by_test_id("login-password-input").fill("admin")
    page10.get_by_test_id("login-password-input").press("Enter")
    time.sleep(1)  # Wait before submit
    page10.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page10.get_by_test_id("main-nav-resources").click()
    time.sleep(2)  # Wait for resources page
    page10.get_by_test_id("machine-remote-rediacc11").click()
    time.sleep(1)  # Wait for menu
    page10.get_by_test_id("function-modal-item-down").click()
    time.sleep(2)  # Wait for action to complete

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
