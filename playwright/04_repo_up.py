import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page8 = context.new_page()
    page8.goto("http://localhost:7322/console/login")
    page8.get_by_role("textbox", name="Email").click()
    page8.get_by_role("textbox", name="Email").fill("admin@rediacc.io")
    page8.get_by_role("textbox", name="Email").press("Tab")
    page8.get_by_role("textbox", name="Password", exact=True).fill("admin")
    page8.get_by_role("textbox", name="Password", exact=True).press("Tab")
    page8.get_by_role("button", name="Sign In").click()
    page8.get_by_text("Resources", exact=True).click()
    page8.get_by_role("cell", name="right desktop rediacc11").locator("span").first.click()
    page8.get_by_role("button", name="function Remote").nth(1).click()
    page8.get_by_text("up", exact=True).click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
