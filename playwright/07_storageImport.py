import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page13 = context.new_page()
    page13.goto("http://localhost:7322/en")
    with page13.expect_popup() as page14_info:
        page13.get_by_role("banner").get_by_role("link", name="Login").click()
    page14 = page14_info.value
    page14.get_by_role("textbox", name="Email").click()
    page14.get_by_role("textbox", name="Email").fill("admin@rediacc.io")
    page14.get_by_role("textbox", name="Email").press("Tab")
    page14.get_by_role("textbox", name="Password", exact=True).fill("admin")
    page14.get_by_role("textbox", name="Password", exact=True).press("Enter")
    page14.get_by_role("button", name="Sign In").click()
    page14.get_by_text("Resources", exact=True).click()
    page14.get_by_role("tab", name="cloud Storage").click()
    page14.get_by_role("button", name="import Import from Rclone").click()
    page14.get_by_text("rclone config file", exact=True).click()
    page14.get_by_role("button", name="upload Click to upload or").click()
    page14.get_by_role("button", name="upload Click to upload or").set_input_files("conf.conf")
    page14.get_by_role("button", name="Import Selected").click()
    page14.locator("button").filter(has_text="Close").click()
    page14.get_by_text("Machines").click()
    page14.get_by_role("cell", name="right desktop rediacc11").locator("span").first.click()
    page14.get_by_role("cell", name="Repositories Last Updated: 3").get_by_role("button").click()
    page14.get_by_text("push").click()
    page14.get_by_text("rediacc11 (Current Machine)").click()
    page14.get_by_text("machine", exact=True).click()
    page14.get_by_title("storage").locator("div").click()
    page14.locator(".ant-select.ant-select-outlined.ant-select-in-form-item.css-kmy92e.ant-select-single.ant-select-show-arrow.ant-select-show-search > .ant-select-selector > .ant-select-selection-wrap > .ant-select-selection-item").click()
    page14.get_by_title("microsoft").locator("div").click()
    page14.get_by_role("button", name="Add to Queue").click()
    page14.get_by_label("Queue Item Trace - 91097afd-").locator("button").filter(has_text="Close").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
