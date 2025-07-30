from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    
    # Navigate to login page
    page.goto("http://localhost:7322/console/login")
    time.sleep(2)  # Wait after page load
    
    # Login
    page.get_by_test_id("login-email-input").click()
    page.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    page.get_by_test_id("login-email-input").press("Tab")
    page.get_by_test_id("login-password-input").fill("admin")
    time.sleep(1)  # Wait after filling password
    page.get_by_test_id("login-submit-button").click()
    time.sleep(3)  # Wait for login to complete
    
    # Navigate to Resources page
    page.get_by_test_id("main-nav-resources").click()
    time.sleep(2)  # Wait for resources page to load
    
    
    
    # Click on the machine's remote button to access repository actions
    page.get_by_test_id("machine-remote-rediacc11").click()
    time.sleep(1)  # Wait for dropdown menu to open
    
    # Click on Create Repo option
    page.get_by_test_id("machine-create-repo-rediacc11").click()
    time.sleep(2)  # Wait for create repo dialog
    
    # Fill repository name
    page.get_by_test_id("resource-modal-field-repositoryName-input").click()
    page.get_by_test_id("resource-modal-field-repositoryName-input").fill("Repo02")
    time.sleep(1)  # Wait after filling name
    
    # Set disk size to 1 GB
    page.get_by_test_id("resource-modal-field-size-size-input").fill("1")
    time.sleep(1)  # Wait after setting disk size
    
    # Select template - expand template selection
    page.get_by_test_id("template-selector-collapsed").click()
    time.sleep(1)  # Wait for template selection to expand
    
    # Select Nginx template
    page.get_by_test_id("template-nginx").click()
    time.sleep(1)  # Wait after selecting template
    
    # Collapse the template panel
    page.get_by_test_id("template-selector-expanded").click()
    time.sleep(1)  # Wait after collapsing
    
    # Generate access password - click on the key icon
    page.get_by_test_id("vault-editor-generate-credential").click()
    time.sleep(1)  # Wait for tooltip to appear
    
    # Click Generate button in the tooltip
    page.get_by_test_id("vault-editor-generate-button").click()
    time.sleep(1)  # Wait for password generation
    
    # Apply the generated password
    page.get_by_test_id("vault-editor-apply-generated").click()
    time.sleep(1)  # Wait after applying password
    
    # Create the repository
    page.get_by_test_id("resource-modal-ok-button").click()
    time.sleep(10)  # Wait for repository creation to complete and see "Done" in Completed
    
    # Close the trace modal (X button in top right)
    page.get_by_test_id("trace-modal-close-button").click()
    time.sleep(2)  # Wait after closing

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
