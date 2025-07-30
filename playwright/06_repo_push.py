import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page11 = context.new_page()
    page11.goto("http://localhost:7322/en")
    with page11.expect_popup() as page12_info:
        page11.get_by_role("banner").get_by_role("link", name="Login").click()
    page12 = page12_info.value
    page12.get_by_role("textbox", name="Email").click()
    page12.get_by_role("textbox", name="Email").fill("admin@rediacc.io")
    page12.get_by_role("textbox", name="Email").press("Tab")
    page12.get_by_role("textbox", name="Password", exact=True).fill("admin")
    page12.get_by_role("button", name="Sign In").click()
    page12.get_by_text("Resources", exact=True).click()
    page12.get_by_role("cell", name="right desktop rediacc11").locator("svg").first.click()
    page12.get_by_role("cell", name="Repositories Last Updated: 3").get_by_role("button").click()
    page12.get_by_text("push").click()
    page12.get_by_text("rediacc11 (Current Machine)").click()
    page12.get_by_title("rediacc12").locator("div").click()
    page12.get_by_role("button", name="Add to Queue").click()
    page12.locator("button").filter(has_text="Close").click()
    page12.get_by_role("cell", name="right desktop rediacc12").locator("path").first.click()
    page12.get_by_role("cell", name="right desktop rediacc12").locator("span").first.click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
