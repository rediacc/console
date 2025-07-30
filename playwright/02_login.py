#!/usr/bin/env python3
import re
import time
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("http://localhost:7322/console/login")
    time.sleep(1)
    page.get_by_role("textbox", name="Email").click()
    time.sleep(1)
    page.get_by_role("textbox", name="Email").fill("anil@rediacc.com")
    time.sleep(1)
    page.get_by_role("textbox", name="Email").press("Tab")
    time.sleep(1)
    page.get_by_role("textbox", name="Password", exact=True).fill("87654321i_")
    time.sleep(1)
    page.get_by_role("button", name="Sign In").click()
    time.sleep(7)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
