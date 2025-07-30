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
        time.sleep(1)
    page2 = page2_info.value
    page2.get_by_test_id("login-email-input").click()
    page2.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page2.get_by_test_id("login-email-input").press("Tab")
    page2.get_by_test_id("login-password-input").fill("admin")
    page2.get_by_test_id("login-submit-button").click()
    time.sleep(3)
    page2.get_by_test_id("main-nav-resources").get_by_text("Resources").click()
    time.sleep(2)
    page2.get_by_test_id("machine-remote-rediacc11").click()
    time.sleep(2)
    page2.get_by_text("Create Repo").click()
    time.sleep(2)
    page2.get_by_test_id("resource-modal-field-repositoryName-input").click()
    time.sleep(1)
    page2.get_by_test_id("resource-modal-field-repositoryName-input").fill("repo03")
    page2.get_by_test_id("resource-modal-field-repositoryName-input").press("Tab")
    time.sleep(1)
    page2.get_by_test_id("resource-modal-field-size-size-input").fill("1")
    time.sleep(1)
    page2.get_by_role("button", name="collapsed appstore Select").click()
    time.sleep(1)
    page2.locator("div:nth-child(9) > .ant-card > .ant-card-body > .ant-space > div").first.click()
    time.sleep(1)
    page2.get_by_role("button", name="expanded appstore Select").click()
    time.sleep(1)
    page2.get_by_test_id("vault-editor-generate-credential").click()
    time.sleep(1)
    page2.get_by_test_id("vault-editor-generate-button").click()
    time.sleep(1)
    page2.get_by_test_id("vault-editor-apply-generated").click()
    time.sleep(1)
    page2.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(10)
    page2.locator("button").filter(has_text="Close").click()
    time.sleep(2)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
