import json
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RepositoryDeleter:
    def __init__(self, config_path="config.json"):
        """Initialize with configuration"""
        self.config = self._load_config(config_path)
        self.page = None
        self.context = None
        self.browser = None
        
    def _load_config(self, config_path):
        """Load configuration from JSON file"""
        config_file = Path(__file__).parent / config_path
        with open(config_file, 'r') as f:
            return json.load(f)
    
    def setup_browser(self, playwright: Playwright):
        """Setup browser with configuration"""
        browser_config = self.config.get('browser', {})
        self.browser = playwright.chromium.launch(
            headless=browser_config.get('headless', False),
            slow_mo=browser_config.get('slowMo', 0)
        )
        
        viewport = browser_config.get('viewport', {})
        self.context = self.browser.new_context(
            viewport={
                'width': viewport.get('width', 1280),
                'height': viewport.get('height', 720)
            }
        )
        self.page = self.context.new_page()
        
        # Set default timeout
        self.page.set_default_timeout(self.config.get('timeouts', {}).get('pageLoad', 30000))
        logger.info("Browser setup completed")
        
    def navigate_to_login(self):
        """Navigate to login page"""
        base_url = self.config.get('baseUrl', 'http://localhost:7322')
        self.page.goto(f"{base_url}/en")
        
        # Wait for page to load and click login
        login_link = self.page.get_by_role("link", name="Sign In")
        login_link.wait_for(state="visible")
        
        # Handle new tab/popup
        with self.page.expect_popup() as popup_info:
            login_link.click()
        
        self.page = popup_info.value
        logger.info("Navigated to login page")
        
    def login(self):
        """Login using credentials from config"""
        credentials = self.config.get('login', {}).get('credentials', {})
        email = credentials.get('email', 'admin@rediacc.io')
        password = credentials.get('password', 'admin')
        
        # Wait for login form to be ready
        email_input = self.page.get_by_test_id("login-email-input")
        email_input.wait_for(state="visible")
        
        # Fill login form
        email_input.fill(email)
        self.page.get_by_test_id("login-password-input").fill(password)
        
        # Submit login
        self.page.get_by_test_id("login-submit-button").click()
        
        # Wait for dashboard to load
        self.page.wait_for_url("**/console/dashboard", timeout=10000)
        logger.info(f"Logged in successfully as {email}")
        
    def navigate_to_repositories(self):
        """Navigate to Resources > Repositories"""
        ui_config = self.config.get('repoDelete', {}).get('ui', {})
        
        # Click Resources menu
        resources_menu = self.page.get_by_test_id(ui_config.get('resourcesMenuTestId', 'main-nav-resources'))
        resources_menu.wait_for(state="visible")
        resources_menu.click()
        
        # Wait for resources page
        self.page.wait_for_url("**/console/resources")
        
        # Click Repositories tab
        repo_tab = self.page.get_by_test_id(ui_config.get('repositoriesTabTestId', 'resources-tab-repositories'))
        repo_tab.wait_for(state="visible")
        repo_tab.click()
        
        # Wait for repository list to load - wait for delete buttons to appear
        ui_config = self.config.get('repoDelete', {}).get('ui', {})
        delete_prefix = ui_config.get('deleteButtonPrefix', 'resources-repository-delete-')
        self.page.wait_for_selector(f"button[data-testid*='{delete_prefix}']", state="visible", timeout=10000)
        logger.info("Navigated to Repositories tab")
        
    def get_repository_list(self):
        """Get list of repositories from the page"""
        # Wait for table to be stable
        self.page.wait_for_load_state("networkidle")
        
        # Wait for repository rows - look for delete buttons to identify repo rows
        ui_config = self.config.get('repoDelete', {}).get('ui', {})
        delete_prefix = ui_config.get('deleteButtonPrefix', 'resources-repository-delete-')
        delete_buttons = self.page.locator(f"button[data-testid*='{delete_prefix}']")
        count = delete_buttons.count()
        
        repositories = []
        for i in range(count):
            button = delete_buttons.nth(i)
            # Extract repository name from the test-id
            test_id = button.get_attribute("data-testid")
            if test_id and test_id.startswith(delete_prefix):
                repo_name = test_id.replace(delete_prefix, "")
                repositories.append(repo_name)
                
        logger.info(f"Found {len(repositories)} repositories: {repositories}")
        return repositories
        
    def delete_repository(self, repo_name=None, repo_index=0):
        """Delete a repository by name or index"""
        repositories = self.get_repository_list()
        
        if not repositories:
            logger.warning("No repositories found to delete")
            return False
            
        # Determine which repository to delete
        if repo_name:
            if repo_name not in repositories:
                logger.warning(f"Repository '{repo_name}' not found")
                return False
            target_repo = repo_name
        else:
            if repo_index >= len(repositories):
                logger.warning(f"Repository index {repo_index} out of range")
                return False
            target_repo = repositories[repo_index]
            
        logger.info(f"Attempting to delete repository: {target_repo}")
        
        # Click delete button for the repository
        delete_button = self.page.get_by_test_id(f"resources-repository-delete-{target_repo}")
        delete_button.wait_for(state="visible")
        delete_button.click()
        logger.info(f"Clicked delete button for repository: {target_repo}")
        
        # Wait for confirmation dialog (Ant Design Modal)
        ui_config = self.config.get('repoDelete', {}).get('ui', {})
        timeouts = self.config.get('repoDelete', {}).get('timeouts', {})
        
        modal_selector = ui_config.get('modalSelector', 'div[role="dialog"]')
        modal = self.page.locator(modal_selector).filter(has_text="Delete Repository")
        modal.wait_for(state="visible", timeout=timeouts.get('modalWait', 5000))
        
        # Verify confirmation message
        content_selector = ui_config.get('modalContentSelector', 'div.ant-modal-confirm-content')
        confirmation_text = modal.locator(content_selector).text_content()
        logger.info(f"Confirmation dialog: {confirmation_text}")
        
        # Click OK button in the modal (Delete button)
        delete_btn_selector = ui_config.get('deleteConfirmButtonSelector', 'button.ant-btn-dangerous')
        ok_button = modal.locator(delete_btn_selector).filter(has_text="Delete")
        ok_button.click()
        
        # Wait for success message (Ant Design notification)
        validation_config = self.config.get('repoDelete', {}).get('validation', {})
        success_messages = validation_config.get('successMessages', [])
        
        # Format success messages with the actual repository name
        formatted_messages = []
        for msg in success_messages:
            formatted_msg = msg.replace('{name}', target_repo)
            formatted_messages.append(formatted_msg)
        
        success_found = False
        notification_selectors = validation_config.get('notificationSelectors', [".ant-message", ".ant-notification", "[role='alert']"])
        timeouts = self.config.get('repoDelete', {}).get('timeouts', {})
        notification_timeout = timeouts.get('notificationWait', 5000)
        
        # Wait a moment for notification to appear
        self.page.wait_for_timeout(500)
        
        # Check for Ant Design message/notification
        for selector in notification_selectors:  
            try:
                # Wait for notification to appear
                notification = self.page.locator(selector).first
                notification.wait_for(state="visible", timeout=notification_timeout)
                notification_text = notification.text_content()
                
                for message in formatted_messages:
                    if message in notification_text:
                        success_found = True
                        logger.info(f"Success message found: {message}")
                        break
                if success_found:
                    break
            except:
                continue
                
        if not success_found:
            logger.warning("No success message found after deletion")
            
        # Wait for the modal to disappear and page to update
        self.page.wait_for_function(
            "() => !document.querySelector('div[role=\"dialog\"]')",
            timeout=5000
        )
        # Wait for network to be idle (API calls to complete)
        self.page.wait_for_load_state("networkidle")
        
        # Verify deletion
        new_repositories = self.get_repository_list()
        if target_repo not in new_repositories:
            logger.info(f"Repository '{target_repo}' successfully deleted")
            return True
        else:
            logger.error(f"Repository '{target_repo}' still exists after deletion attempt")
            return False
            
    def cleanup(self):
        """Cleanup browser resources"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        logger.info("Browser cleanup completed")


def run(playwright: Playwright) -> None:
    """Main execution function"""
    deleter = RepositoryDeleter()
    
    try:
        # Setup browser
        deleter.setup_browser(playwright)
        
        # Navigate and login
        deleter.navigate_to_login()
        deleter.login()
        
        # Navigate to repositories
        deleter.navigate_to_repositories()
        
        # Delete repository based on config
        test_config = deleter.config.get('repoDelete', {}).get('test', {})
        target_repo = test_config.get('targetRepository')
        target_index = test_config.get('targetIndex', 0)
        delete_by_name = test_config.get('deleteByName', False)
        
        if delete_by_name and target_repo:
            success = deleter.delete_repository(repo_name=target_repo)
        else:
            success = deleter.delete_repository(repo_index=target_index)
        
        if success:
            logger.info("Repository deletion completed successfully")
        else:
            logger.error("Repository deletion failed")
            
        # Keep browser open for a moment to see the result
        deleter.page.wait_for_timeout(2000)
        
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        # Take screenshot on error
        if deleter.page:
            screenshot_path = Path(__file__).parent / "error_screenshot.png"
            deleter.page.screenshot(path=str(screenshot_path))
            logger.info(f"Error screenshot saved to: {screenshot_path}")
    finally:
        # Cleanup
        deleter.cleanup()


def main():
    """Main entry point"""
    with sync_playwright() as playwright:
        run(playwright)


if __name__ == "__main__":
    main()