import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page1 = context.new_page()
    page1.goto("http://localhost:7322/en")
    time.sleep(2)
    with page1.expect_popup() as page2_info:
        page1.get_by_role("banner").get_by_role("link", name="Login").click()
    page2 = page2_info.value
    page2.get_by_test_id("login-email-input").click()
    page2.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page2.get_by_test_id("login-email-input").press("Tab")
    page2.get_by_test_id("login-password-input").fill("admin")
    page2.get_by_test_id("login-submit-button").click()
    time.sleep(3)
    page2.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    time.sleep(2)
    page2.get_by_test_id("machine-expand-rediacc11").locator("path").click()
    time.sleep(2)
    page2.get_by_test_id("machine-repo-list-repo-actions-Repo001").click()
    time.sleep(1)
    page2.get_by_text("down").click()
    time.sleep(1)
    page2.get_by_test_id("queue-trace-close-button").click()
    time.sleep(1)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
