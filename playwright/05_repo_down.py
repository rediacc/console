import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page9 = context.new_page()
    page9.goto("http://localhost:7322/en")
    with page9.expect_popup() as page10_info:
        page9.get_by_role("banner").get_by_role("link", name="Login").click()
    page10 = page10_info.value
    page10.get_by_role("textbox", name="Email").click()
    page10.get_by_role("textbox", name="Email").fill("admin@rediacc.io")
    page10.get_by_role("textbox", name="Email").press("Tab")
    page10.get_by_role("textbox", name="Password", exact=True).fill("admin")
    page10.get_by_role("textbox", name="Password", exact=True).press("Enter")
    page10.get_by_role("button", name="Sign In").click()
    page10.get_by_text("Resources", exact=True).click()
    page10.get_by_role("cell", name="right desktop rediacc11").locator("svg").first.click()
    page10.get_by_role("button", name="function Remote").nth(1).click()
    page10.get_by_text("down").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
