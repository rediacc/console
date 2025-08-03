import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page9 = context.new_page()
    page9.goto("http://localhost:7322/en")
    time.sleep(2)
    with page9.expect_popup() as page10_info:
        page9.get_by_role("banner").get_by_role("link", name="Login").click()
    page10 = page10_info.value
    time.sleep(1)
    page10.get_by_test_id("login-email-input").click()
    page10.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    time.sleep(0.5)
    page10.get_by_test_id("login-email-input").press("Tab")
    page10.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page10.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page10.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    time.sleep(1.5)
    page10.get_by_test_id("machine-expand-rediacc11").click()
    time.sleep(1)
    page10.get_by_test_id("machine-repo-list-table").get_by_role("img", name="right").locator("svg").click()
    time.sleep(1)
    page10.get_by_test_id("machine-repo-list-container-actions-edbcc7482431").click()
    time.sleep(0.5)
    page10.get_by_text("container_pause").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
