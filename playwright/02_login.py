#!/usr/bin/env python3
import time
from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("http://localhost:7322/console/login")
    time.sleep(1)
    page.get_by_test_id("login-email-input").click()
    time.sleep(1)
    page.get_by_test_id("login-email-input").fill("anil@rediacc.com")
    time.sleep(1)
    page.get_by_test_id("login-email-input").press("Tab")
    time.sleep(1)
    page.get_by_test_id("login-password-input").fill("87654321i_")
    time.sleep(1)
    page.get_by_test_id("login-submit-button").click()
    time.sleep(7)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
