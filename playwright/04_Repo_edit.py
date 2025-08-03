import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page3 = context.new_page()
    page3.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    
    with page3.expect_popup() as page4_info:
        page3.get_by_role("banner").get_by_role("link", name="Login").click()
    page4 = page4_info.value
    time.sleep(1)  # Wait for login page to load
    
    page4.get_by_test_id("login-email-input").click()
    time.sleep(0.5)
    page4.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    time.sleep(0.5)
    page4.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)
    page4.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Pause before submitting
    page4.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    
    page4.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    time.sleep(1)  # Wait for resources menu to open
    page4.get_by_test_id("resources-tab-repositories").click()
    time.sleep(1.5)  # Wait for repositories tab to load
    page4.get_by_test_id("resources-repository-edit-repo006").click()
    time.sleep(1)  # Wait for edit modal to open
    
    page4.get_by_test_id("resource-modal-field-repositoryName-input").click()
    time.sleep(0.5)
    page4.get_by_test_id("resource-modal-field-repositoryName-input").fill("repo006")
    time.sleep(1)  # Pause after entering repository name
    page4.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(2)  # Wait for update to complete

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
