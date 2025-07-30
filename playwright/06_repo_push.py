from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page11 = context.new_page()
    page11.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    
    # Click login link in the main page
    page11.get_by_test_id("banner-login-link").click()
    time.sleep(1)  # Wait for login page
    
    # Wait for login page and fill credentials
    page11.get_by_test_id("login-email-input").click()
    page11.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page11.get_by_test_id("login-email-input").press("Tab")
    page11.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait before submit
    page11.get_by_test_id("login-submit-button").click()
    time.sleep(2)  # Wait for login to complete
    
    # Navigate to Resources page
    page11.get_by_test_id("main-nav-resources").click()
    time.sleep(2)  # Wait for resources page
    
    # Click on a machine row to expand it (rediacc11)
    page11.get_by_test_id("machine-row-rediacc11").click()
    time.sleep(1)  # Wait for expansion
    
    # Click on the Remote button for a repository
    page11.get_by_test_id("machine-repo-list-repo-actions-push").click()
    time.sleep(1)  # Wait for menu
    
    # Select push function
    page11.get_by_test_id("function-push").click()
    time.sleep(1)  # Wait for push dialog
    
    # Select current machine (rediacc11)
    page11.get_by_test_id("push-source-rediacc11").click()
    time.sleep(0.5)
    
    # Select target machine (rediacc12)
    page11.get_by_test_id("push-target-rediacc12").click()
    time.sleep(0.5)
    
    # Click Add to Queue button
    page11.get_by_test_id("push-add-to-queue-button").click()
    time.sleep(2)  # Wait for queue action
    
    # Close the modal
    page11.get_by_test_id("modal-close-button").click()
    time.sleep(1)
    
    # Click on another machine row to expand it (rediacc12)
    page11.get_by_test_id("machine-row-rediacc12").click()
    time.sleep(1)

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
