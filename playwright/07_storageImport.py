from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page13 = context.new_page()
    page13.goto("http://localhost:7322/en")
    with page13.expect_popup() as page14_info:
        page13.get_by_test_id("header-login-link").click()
    page14 = page14_info.value
    page14.get_by_test_id("login-email-input").click()
    page14.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page14.get_by_test_id("login-email-input").press("Tab")
    page14.get_by_test_id("login-password-input").fill("admin")
    page14.get_by_test_id("login-password-input").press("Enter")
    page14.get_by_test_id("login-submit-button").click()
    page14.get_by_test_id("nav-resources").click()
    page14.get_by_test_id("resources-tab-storage").click()
    page14.get_by_test_id("resources-import-button").click()
    page14.get_by_test_id("rclone-wizard-upload-dragger").click()
    page14.get_by_test_id("rclone-wizard-upload-dragger").set_input_files("conf.conf")
    page14.get_by_test_id("rclone-wizard-import-button").click()
    page14.get_by_test_id("rclone-wizard-close-button").click()
    page14.get_by_test_id("nav-machines").click()
    page14.get_by_test_id("machine-row-rediacc11").click()
    page14.get_by_test_id("machine-repositories-button-rediacc11").click()
    page14.get_by_test_id("repo-action-push").click()
    page14.get_by_test_id("push-current-machine-radio").click()
    page14.get_by_test_id("push-target-machine-radio").click()
    page14.get_by_test_id("push-storage-selector").click()
    page14.get_by_test_id("push-storage-selection").click()
    page14.get_by_test_id("push-storage-option-microsoft").click()
    page14.get_by_test_id("push-add-to-queue-button").click()
    page14.get_by_test_id("queue-trace-modal-close-button").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
