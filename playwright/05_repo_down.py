from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page9 = context.new_page()
    page9.goto("http://localhost:7322/en")
    with page9.expect_popup() as page10_info:
        page9.get_by_test_id("banner-login-link").click()
    page10 = page10_info.value
    page10.get_by_test_id("login-email-input").click()
    page10.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page10.get_by_test_id("login-email-input").press("Tab")
    page10.get_by_test_id("login-password-input").fill("admin")
    page10.get_by_test_id("login-password-input").press("Enter")
    page10.get_by_test_id("login-submit-button").click()
    page10.get_by_test_id("main-nav-resources").click()
    page10.get_by_test_id("machine-remote-rediacc11").click()
    page10.get_by_test_id("function-modal-item-down").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
