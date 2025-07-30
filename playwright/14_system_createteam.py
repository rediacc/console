import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page20 = context.new_page()
    page20.goto("http://localhost:7322/en")
    with page20.expect_popup() as page21_info:
        page20.get_by_test_id("banner-login-link").click()
    page21 = page21_info.value
    page21.get_by_test_id("login-email-input").click()
    page21.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page21.get_by_test_id("login-email-input").press("Tab")
    page21.get_by_test_id("login-password-input").fill("admin")
    page21.get_by_test_id("login-submit-button").click()
    page21.get_by_test_id("main-nav-system").click()
    page21.get_by_test_id("system-tab-teams").click()
    page21.get_by_test_id("system-create-team-button").click()
    page21.get_by_test_id("resource-modal-field-teamName-input").click()
    page21.get_by_test_id("resource-modal-field-teamName-input").fill("test2")
    page21.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY").click()
    page21.get_by_test_id("vault-editor-generate-button").click()
    page21.get_by_test_id("vault-editor-apply-generated").click()
    page21.get_by_test_id("resource-modal-ok-button").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
