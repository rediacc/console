#!/usr/bin/env python3
"""
Create Repository Test - Refactored to use SmartTestBase
"""

import sys
from pathlib import Path
from playwright.sync_api import Page

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from smart_test_base import SmartTestBase


class CreateRepoTest(SmartTestBase):
    """Test class for creating a repository."""
    
    def __init__(self):
        """Initialize create repository test."""
        super().__init__("CreateRepoTest")
    
    def select_machine_and_open_create(self, page: Page, machine_name: str) -> bool:
        """Select machine and open create repo dialog."""
        try:
            # Click on the machine's remote button
            self.log_info(f"Selecting machine: {machine_name}")
            
            machine_remote = page.get_by_test_id(f"machine-remote-{machine_name}")
            machine_remote.wait_for(state="visible", timeout=5000)
            machine_remote.click()
            
            # Wait for context menu and click Create Repo
            self.log_info("Opening Create Repo dialog")
            create_repo_menu = page.get_by_text("Create Repo")
            create_repo_menu.wait_for(state="visible", timeout=5000)
            create_repo_menu.click()
            
            return self.wait_for_modal(page)
            
        except Exception as e:
            self.log_error(f"Failed to open create repo dialog: {str(e)}")
            return False
    
    def fill_repository_details(self, page: Page) -> str:
        """Fill repository creation form."""
        repo_config = self.config["createRepo"]
        
        # Use session repository name
        repo_name = self.get_session_repository_name()
        self.log_info(f"Repository name: {repo_name}")
        
        # Fill repository name
        if not self.fill_modal_field(page, "repositoryName", repo_name):
            # Fallback to direct selector
            repo_name_input = page.get_by_test_id("resource-modal-field-repositoryName-input")
            repo_name_input.fill(repo_name)
        
        # Fill repository size
        repo_size = repo_config["repositorySize"]
        self.log_info(f"Repository size: {repo_size}G")
        
        size_input = page.get_by_test_id("resource-modal-field-size-size-input")
        size_input.wait_for(state="visible")
        size_input.clear()
        size_input.fill(repo_size)
        
        return repo_name
    
    def select_template(self, page: Page, template: str) -> bool:
        """Select a template for the repository."""
        if not template or template == "none":
            return True
            
        try:
            self.log_info(f"Selecting template: {template}")
            
            # Click to expand template selector
            template_button = page.get_by_role("button", name="collapsed appstore Select")
            template_button.wait_for(state="visible", timeout=5000)
            template_button.click()
            
            # Wait for template list
            page.wait_for_selector('.ant-card', state="visible", timeout=5000)
            
            # Select the template
            if template.lower() == "nginx":
                nginx_template = page.locator('text=NginxMinimal Nginx web server')
                nginx_template.click()
            else:
                template_selector = page.locator(f'text={template}').first
                template_selector.click()
            
            # Collapse template selector
            template_button_expanded = page.get_by_role("button", name="expanded appstore Select")
            template_button_expanded.click()
            
            return True
            
        except Exception as e:
            self.log_warning(f"Failed to select template: {str(e)}")
            return False
    
    def generate_password(self, page: Page) -> bool:
        """Generate a random password for the repository."""
        try:
            self.log_info("Generating random password")
            
            # Click password generation icon
            password_gen_icon = page.get_by_test_id("vault-editor-generate-credential")
            password_gen_icon.click()
            
            # Click Generate button
            generate_button = page.get_by_test_id("vault-editor-generate-button")
            generate_button.wait_for(state="visible")
            generate_button.click()
            
            # Wait for success
            page.wait_for_selector('text=Generated successfully', state="visible", timeout=5000)
            
            # Apply the generated password
            apply_button = page.get_by_test_id("vault-editor-apply-generated")
            apply_button.click()
            
            # Wait for apply success
            page.wait_for_selector('text=Values applied successfully', state="visible", timeout=5000)
            
            return True
            
        except Exception as e:
            self.log_warning(f"Failed to generate password: {str(e)}")
            return False
    
    def submit_and_wait_for_completion(self, page: Page) -> bool:
        """Submit repository creation and wait for completion."""
        try:
            # Click Create button
            self.log_info("Creating repository")
            create_button = page.get_by_test_id("resource-modal-ok-button")
            create_button.click()
            
            # Wait for Queue Item Trace dialog
            queue_timeout = self.config["createRepo"].get("queueTimeout", 120000)
            
            page.wait_for_selector('[role="dialog"]:has-text("Queue Item Trace")', 
                                 state="visible", 
                                 timeout=queue_timeout)
            self.log_info("Queue Item Trace dialog opened")
            
            # Wait for task completion
            self.log_info("Waiting for task completion")
            
            # Look for success alert
            success_alert = page.wait_for_selector(
                '.ant-alert-success:has-text("Task Completed Successfully")', 
                state="visible", 
                timeout=queue_timeout
            )
            
            if success_alert:
                self.log_success("Task Completed Successfully")
                
                # Try to get duration
                try:
                    duration_text = page.locator('.ant-alert-success:has-text("The task finished successfully after")').text_content()
                    if duration_text and "after" in duration_text:
                        self.log_info(duration_text.strip())
                except:
                    pass
                
                # Close dialog
                try:
                    close_button = page.locator('button:has-text("Close")').last
                    close_button.click()
                    self.log_info("Closed Queue Item Trace dialog")
                except:
                    self.log_warning("Could not close Queue Item Trace dialog")
                
                return True
                
        except Exception as e:
            self.log_error(f"Repository creation failed or timed out: {str(e)}")
            return False
    
    def run_with_page(self, page: Page) -> bool:
        """Execute the create repository test with existing page/session."""
        try:
            repo_config = self.config["createRepo"]
            
            # Navigate to resources page
            if not self.navigate_to_resources(page):
                return False
            
            # Select machine and open create dialog
            machine_name = repo_config["machineName"]
            if not self.select_machine_and_open_create(page, machine_name):
                return False
            
            # Fill repository details
            repo_name = self.fill_repository_details(page)
            
            # Select template if configured
            template = repo_config.get("template")
            if template:
                self.select_template(page, template)
            
            # Generate password if configured
            if repo_config.get("generatePassword", False):
                self.generate_password(page)
            
            # Submit and wait for completion
            if not self.submit_and_wait_for_completion(page):
                return False
            
            self.log_success(f"Repository '{repo_name}' created successfully!")
            
            # Take success screenshot
            self.take_screenshot(page, f"createrepo_success_{repo_name}")
            
            return True
            
        except Exception as e:
            self.log_error(f"Test failed with exception: {str(e)}")
            self.take_screenshot(page, "createrepo_exception")
            return False


# Wrapper function for backward compatibility with test_suite_runner.py
def run_with_page(page: Page, config: dict) -> str:
    """Run the repository creation with existing page/session."""
    test = CreateRepoTest()
    success = test.run_with_page(page)
    return test.get_session_repository_name() if success else None


# Standalone execution removed - use test_suite_runner.py to run tests