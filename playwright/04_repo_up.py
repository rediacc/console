from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page8 = context.new_page()
    page8.goto("http://localhost:7322/console/login")
    page8.get_by_test_id("login-email-input").click()
    page8.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page8.get_by_test_id("login-email-input").press("Tab")
    page8.get_by_test_id("login-password-input").fill("admin")
    page8.get_by_test_id("login-password-input").press("Tab")
    page8.get_by_test_id("login-submit-button").click()
    page8.get_by_test_id("main-nav-resources").click()
    # Click on the machine row for rediacc11
    page8.get_by_test_id("machine-row-rediacc11").click()
    # Click on the Remote button for rediacc11
    page8.get_by_test_id("machine-remote-rediacc11").click()
    # Click on the "up" function
    page8.get_by_test_id("machine-function-up-rediacc11").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
