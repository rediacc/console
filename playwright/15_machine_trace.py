from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page4 = context.new_page()
    page4.goto("http://localhost:7322/console")
    time.sleep(2)  # Wait for page to load
    with page4.expect_popup() as page5_info:
        page4.get_by_role("banner").get_by_role("link", name="Login").click()
    page5 = page5_info.value
    time.sleep(1)  # Wait for login page
    page5.get_by_test_id("login-email-input").click()
    page5.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page5.get_by_test_id("login-email-input").press("Tab")
    page5.get_by_test_id("login-password-input").fill("admin")
    page5.get_by_test_id("login-password-input").press("Enter")
    time.sleep(1)  # Wait before submit
    page5.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page5.get_by_test_id("main-nav-resources").click()
    time.sleep(2)  # Wait for resources page
    page5.get_by_test_id("machine-trace-rediacc11").click()
    time.sleep(2)  # Wait for trace to load
    page5.get_by_test_id("trace-column-updated").click()
    time.sleep(1)  # Wait for sort
    page5.get_by_test_id("trace-column-created").click()
    time.sleep(1)  # Wait for sort

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
