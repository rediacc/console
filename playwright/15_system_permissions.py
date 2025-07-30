import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page22 = context.new_page()
    page22.goto("http://localhost:7322/en")
    with page22.expect_popup() as page23_info:
        page22.get_by_test_id("banner-login-link").click()
    page23 = page23_info.value
    page23.locator(".ant-input-affix-wrapper").first.click()
    page23.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page23.get_by_test_id("login-email-input").press("Tab")
    page23.get_by_test_id("login-password-input").fill("admin")
    page23.get_by_test_id("login-submit-button").click()
    page23.get_by_test_id("main-nav-system").click()
    page23.get_by_test_id("system-tab-permissions").click()
    page23.get_by_test_id("system-create-permission-group-button").click()
    page23.get_by_test_id("system-permission-group-name-input").click()
    page23.get_by_test_id("system-permission-group-name-input").fill("testgroup")
    page23.get_by_test_id("permission-modal-ok-button").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
