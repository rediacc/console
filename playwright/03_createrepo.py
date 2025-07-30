import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page4 = context.new_page()
    page4.goto("http://localhost:7322/console/login")
    page4.get_by_label("global").locator("svg").click()
    page4.locator("span").filter(has_text="🇬🇧 English").nth(1).click()
    page4.get_by_text("🇫🇷 Français").click()
    page4.get_by_role("textbox", name="Email").click()
    page4.get_by_role("textbox", name="Email").fill("admin@rediacc.io")
    page4.get_by_role("textbox", name="Email").press("Tab")
    page4.get_by_role("textbox", name="Password", exact=True).fill("admin")
    page4.get_by_role("button", name="Sign In").click()
    page4.get_by_text("Resources", exact=True).click()
    page4.get_by_role("button", name="plus Add Machine").click()
    page4.get_by_role("button", name="Cancel").click()
    page4.get_by_role("button", name="plus Add Machine").click()
    page4.get_by_role("button", name="Cancel").click()
    page4.get_by_role("button", name="function Remote").first.click()
    page4.get_by_role("button", name="function Remote").first.click()
    page4.get_by_role("button", name="function Remote").first.click()
    page4.get_by_text("Create Repo").click()
    page4.get_by_role("textbox", name="Enter repository name").click()
    page4.get_by_role("textbox", name="Enter repository name").press("CapsLock")
    page4.get_by_role("textbox", name="Enter repository name").fill("R")
    page4.get_by_role("textbox", name="Enter repository name").press("CapsLock")
    page4.get_by_role("textbox", name="Enter repository name").fill("Repo01")
    page4.get_by_role("textbox", name="Enter repository name").press("Tab")
    page4.get_by_role("spinbutton", name="100").fill("1")
    page4.get_by_role("button", name="collapsed appstore Select").click()
    page4.locator("div:nth-child(9) > .ant-card > .ant-card-body > .ant-space > div").first.click()
    page4.get_by_role("button", name="expanded appstore Select").click()
    page4.get_by_role("textbox", name="* Access Password info-circle").click()
    page4.get_by_role("button", name="key").click()
    page4.get_by_role("button", name="key Generate").click()
    page4.get_by_role("button", name="Apply").click()
    page4.get_by_role("button", name="Create").click()
    page4.locator("button").filter(has_text="Close").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
