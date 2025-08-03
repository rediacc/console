from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page10 = context.new_page()
    page10.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page10.expect_popup() as page11_info:
        page10.get_by_role("banner").get_by_role("link", name="Login").click()
    page11 = page11_info.value
    time.sleep(1)  # Wait for login page
    page11.get_by_test_id("login-email-input").click()
    page11.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page11.get_by_test_id("login-email-input").press("Tab")
    page11.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page11.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page11.get_by_test_id("main-nav-resources").click()
    time.sleep(2)  # Wait for resources page
    page11.get_by_test_id("machine-delete-rediacc11").click()
    time.sleep(1)  # Wait for confirmation dialog
    page11.get_by_test_id("confirm-delete-button").click()
    time.sleep(2)  # Wait for delete to complete

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
