from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page8 = context.new_page()
    page8.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page8.expect_popup() as page9_info:
        page8.get_by_test_id("banner-login-link").click()
    page9 = page9_info.value
    time.sleep(1)  # Wait for login page
    page9.get_by_test_id("login-email-input").click()
    page9.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page9.get_by_test_id("login-email-input").press("Tab")
    page9.get_by_test_id("login-password-input").fill("admin")
    page9.get_by_test_id("login-password-input").press("Enter")
    time.sleep(1)  # Wait before submit
    page9.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page9.get_by_test_id("main-nav-resources").click()
    time.sleep(2)  # Wait for resources page
    page9.get_by_test_id("resources-tab-repositories").click()
    time.sleep(1)  # Wait for repositories tab
    page9.get_by_test_id("resources-repository-delete-a22").click()
    time.sleep(1)  # Wait for confirmation dialog
    page9.get_by_test_id("confirm-delete-button").click()
    time.sleep(2)  # Wait for delete to complete

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
