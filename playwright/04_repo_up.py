import re
from playwright.sync_api import Playwright, sync_playwright, expect
import time

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page1 = context.new_page()
    page1.goto("http://localhost:7322/en")
    with page1.expect_popup() as page2_info:
        page1.get_by_role("banner").get_by_role("link", name="Login").click()
    page2 = page2_info.value
    page2.get_by_test_id("login-email-input").click()
    page2.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page2.get_by_test_id("login-email-input").press("Tab")
    page2.get_by_test_id("login-password-input").fill("admin")
    page2.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    page2.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    time.sleep(1.5)  # Wait for resources page to load
    page2.get_by_test_id("machine-expand-rediacc11").locator("svg").click()
    time.sleep(2)  # Wait for machine expansion
    page2.get_by_role("row", name="right inbox Repo02 function Remote desktop Local down", exact=True).get_by_role("button").first.click()
    time.sleep(1.5)  # Wait for menu to appear
    page2.get_by_text("up", exact=True).click()
    time.sleep(2)  # Wait for up operation to start
    page2.locator("button").filter(has_text="Close").click()
    time.sleep(1)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
