from playwright.sync_api import Playwright, sync_playwright


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page11 = context.new_page()
    page11.goto("http://localhost:7322/en")
    
    # Click login link in the main page
    page11.get_by_test_id("banner-login-link").click()
    
    # Wait for login page and fill credentials
    page11.get_by_test_id("login-email-input").click()
    page11.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page11.get_by_test_id("login-email-input").press("Tab")
    page11.get_by_test_id("login-password-input").fill("admin")
    page11.get_by_test_id("login-submit-button").click()
    
    # Navigate to Resources page
    page11.get_by_test_id("main-nav-resources").click()
    
    # Click on a machine row to expand it (rediacc11)
    page11.get_by_test_id("machine-row-rediacc11").click()
    
    # Click on the Remote button for a repository
    page11.get_by_test_id("machine-repo-list-repo-actions-push").click()
    
    # Select push function
    page11.get_by_test_id("function-push").click()
    
    # Select current machine (rediacc11)
    page11.get_by_test_id("push-source-rediacc11").click()
    
    # Select target machine (rediacc12)
    page11.get_by_test_id("push-target-rediacc12").click()
    
    # Click Add to Queue button
    page11.get_by_test_id("push-add-to-queue-button").click()
    
    # Close the modal
    page11.get_by_test_id("modal-close-button").click()
    
    # Click on another machine row to expand it (rediacc12)
    page11.get_by_test_id("machine-row-rediacc12").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
