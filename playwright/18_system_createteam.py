import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page20 = context.new_page()
    page20.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page20.expect_popup() as page21_info:
        page20.get_by_role("banner").get_by_role("link", name="Login").click()
    page21 = page21_info.value
    time.sleep(1)  # Wait for login page
    page21.get_by_test_id("login-email-input").click()
    page21.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page21.get_by_test_id("login-email-input").press("Tab")
    page21.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page21.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page21.get_by_test_id("main-nav-system").click()
    time.sleep(2)  # Wait for system page
    page21.get_by_test_id("system-tab-teams").click()
    time.sleep(1)  # Wait for teams tab
    page21.get_by_test_id("system-create-team-button").click()
    time.sleep(1)  # Wait for create dialog
    page21.get_by_test_id("resource-modal-field-teamName-input").click()
    page21.get_by_test_id("resource-modal-field-teamName-input").fill("test2")
    time.sleep(0.5)
    page21.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY").click()
    time.sleep(0.5)
    page21.get_by_test_id("vault-editor-generate-button").click()
    time.sleep(1)  # Wait for generation
    page21.get_by_test_id("vault-editor-apply-generated").click()
    time.sleep(0.5)
    page21.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(2)  # Wait for team creation

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
