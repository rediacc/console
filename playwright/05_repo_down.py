from playwright.sync_api import Playwright, sync_playwright
import time


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page9 = context.new_page()
    page9.goto("http://localhost:7322/en")
    time.sleep(2)  # Wait for page to load
    with page9.expect_popup() as page10_info:
        page9.get_by_role("banner").get_by_role("link", name="Login").click()
    page10 = page10_info.value
    time.sleep(2)  # Wait for login page to fully load
    page10.get_by_test_id("login-email-input").click()
    time.sleep(0.5)  # Brief pause
    page10.get_by_test_id("login-email-input").fill("admin@rediacc.io")
    time.sleep(0.5)  # Pause after entering email
    page10.get_by_test_id("login-email-input").press("Tab")
    time.sleep(0.5)  # Pause before password
    page10.get_by_test_id("login-password-input").fill("admin")
    time.sleep(0.5)  # Pause after entering password
    page10.get_by_test_id("login-password-input").press("Enter")
    time.sleep(1)  # Wait before submit
    page10.get_by_test_id("login-submit-button").click()
    time.sleep(3)  # Wait for login to complete and dashboard to load
    page10.get_by_test_id("main-nav-resources").click()
    time.sleep(3)  # Wait for resources page to fully load
    
    # Expand the rediacc11 machine to see repositories
    page10.get_by_test_id("machine-expand-rediacc11").get_by_role("img", name="right").click()
    time.sleep(2)  # Wait for expansion animation and data load
    
    # Look for Repo034 which has a Local down button, or use repo03 after mounting it
    # Try to click on the Local down button for Repo034
    try:
        # If Repo034 exists and has a Local down button
        time.sleep(1)  # Pause before looking for button
        page10.get_by_role("button", name="desktop Local down").click()
        time.sleep(3)  # Wait for action menu or completion
    except:
        # If not found, try to mount repo03 first
        time.sleep(1)  # Pause before trying repo03
        page10.get_by_test_id("machine-repo-list-repo-actions-repo03").click()
        time.sleep(2)  # Wait for menu to appear
        page10.get_by_role("menuitem", name="play-circle up").click()
        time.sleep(5)  # Wait for mount operation to complete
        
        # Now try to click down on repo03
        page10.get_by_test_id("machine-repo-list-repo-actions-repo03").click()
        time.sleep(2)  # Wait for menu to appear again
        page10.get_by_role("menuitem", name="stop-circle down").click()
        time.sleep(3)  # Wait for unmount action to complete

    # ---------------------
    time.sleep(2)  # Final pause before closing
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
