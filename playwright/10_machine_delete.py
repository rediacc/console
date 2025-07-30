from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page10 = context.new_page()
    page10.goto("http://localhost:7322/en")
    with page10.expect_popup() as page11_info:
        page10.get_by_test_id("banner-login-link").click()
    page11 = page11_info.value
    page11.get_by_test_id("login-email-input").click()
    page11.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page11.get_by_test_id("login-email-input").press("Tab")
    page11.get_by_test_id("login-password-input").fill("admin")
    page11.get_by_test_id("login-submit-button").click()
    page11.get_by_test_id("main-nav-resources").click()
    page11.get_by_test_id("machine-delete-rediacc11").click()
    page11.get_by_test_id("confirm-delete-button").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
