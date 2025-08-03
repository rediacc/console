import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page36 = context.new_page()
    page36.goto("http://localhost:7322/en")
    time.sleep(2)
    with page36.expect_popup() as page37_info:
        page36.get_by_role("banner").get_by_role("link", name="Login").click()
    page37 = page37_info.value
    time.sleep(1)
    page37.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page37.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page37.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page37.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)
    page37.get_by_test_id("login-submit-button").click()
    time.sleep(2)
    page37.get_by_text("System").click()
    time.sleep(1.5)
    page37.get_by_test_id("system-create-region-button").click()
    time.sleep(1)
    page37.get_by_test_id("resource-modal-field-regionName-input").click()
    time.sleep(0.5)
    page37.get_by_test_id("resource-modal-field-regionName-input").fill("region004")
    page37.get_by_text("regions.createRegionRegion").click()
    time.sleep(1)
    page37.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
