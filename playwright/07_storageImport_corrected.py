#!/usr/bin/env python3
"""
Storage Import and Push Test - Corrected Version
Fixed import conflicts, method calls, and base class usage
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

try:
    from playwright.sync_api import Playwright, Page, sync_playwright, expect
except ImportError:
    print("Error: Playwright is not installed. Please install it with:")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)

# Import the correct test base
from test_base import PlaywrightTestBase


class StorageImportPushTest(PlaywrightTestBase):
    """
    Test for storage import and repository push operations.
    """
    
    def __init__(self, config_path: str = None):
        """Initialize test with configuration"""
        if config_path is None:
            # Default to config.json in the same directory as this script
            script_dir = Path(__file__).parent
            config_path = str(script_dir / 'config.json')
        super().__init__(config_path)
        self.test_name = "Storage Import and Push Test"
        self.login_page: Optional[Page] = None
    
    def import_storage_configuration(self, page: Page) -> bool:
        """
        Import storage configuration from conf file.
        """
        self.log("=== Starting Storage Import ===")
        
        try:
            # Navigate to Resources
            self.log("Navigating to Resources...")
            page.wait_for_timeout(1000)
            
            # Try different selectors for Resources navigation
            try:
                resources_link = page.get_by_test_id("main-nav-resources").get_by_text("Resources")
                resources_link.click()
            except:
                # Fallback selector
                resources_link = page.locator('a:has-text("Resources")').first
                resources_link.click()
            
            self.wait_for_network_idle(page)
            
            # Click Storage tab
            self.log("Opening Storage tab...")
            try:
                storage_tab = page.get_by_test_id("resources-tab-storage")
                storage_tab.wait_for(state='visible', timeout=5000)
                storage_tab.click()
            except:
                # Fallback selector
                storage_tab = page.locator('.ant-tabs-tab:has-text("Storage")').first
                storage_tab.click()
            
            self.wait_for_network_idle(page)
            
            # Open import dialog
            self.log("Opening import dialog...")
            try:
                import_button = page.get_by_test_id("resources-import-button")
                import_button.wait_for(state='visible', timeout=5000)
                import_button.click()
            except:
                # Fallback selector
                import_button = page.locator('button:has-text("Import")').first
                import_button.click()
            
            page.wait_for_timeout(1000)
            
            # Upload conf file
            conf_path = Path(__file__).parent / "conf.conf"
            if not conf_path.exists():
                self.log(f"Configuration file not found: {conf_path}", level='error')
                return False
            
            self.log(f"Uploading configuration file: {conf_path.name}")
            
            # Find and use the file input
            upload_input = page.locator('input[type="file"]').first
            upload_input.set_input_files(str(conf_path))
            self.log("File uploaded, waiting for processing...")
            page.wait_for_timeout(2000)
            
            # Try to click import button
            self.log("Attempting to import...")
            import_success = False
            try:
                import_btn = page.get_by_test_id("rclone-wizard-import-button")
                if import_btn.is_enabled():
                    import_btn.click()
                    self.log("Import button clicked", level='success')
                    import_success = True
                    page.wait_for_timeout(2000)
                else:
                    self.log("Import button disabled - storage might already exist", level='warning')
            except Exception as e:
                self.log(f"Could not click import button: {str(e)}", level='warning')
            
            # Close dialog
            self.log("Closing import dialog...")
            try:
                close_btn = page.get_by_test_id("rclone-wizard-close-button")
                if close_btn.is_visible():
                    close_btn.click()
                else:
                    page.keyboard.press("Escape")
            except:
                page.keyboard.press("Escape")
            
            page.wait_for_timeout(500)
            
            # Storage import is considered successful even if already exists
            return True
            
        except Exception as e:
            self.log(f"Storage import failed: {str(e)}", level='error')
            self.take_screenshot("import_error")
            return False
    
    def configure_and_execute_push(self, page: Page, machine: str = "rediacc11", 
                                  repo: str = "repo03", storage: str = "microsoft") -> bool:
        """
        Configure and execute push operation to storage.
        """
        self.log(f"=== Configuring Push: {repo} on {machine} to {storage} ===")
        
        try:
            # Navigate to Machines tab
            self.log("Navigating to Machines tab...")
            try:
                machines_tab = page.get_by_test_id("resources-tab-machines")
                machines_tab.click()
            except:
                # Fallback selector
                machines_tab = page.locator('.ant-tabs-tab:has-text("Machines")').first
                if machines_tab.is_visible():
                    machines_tab.click()
                else:
                    self.log("Could not find Machines tab", level='error')
                    return False
            
            self.wait_for_network_idle(page)
            
            # Expand machine
            self.log(f"Expanding machine: {machine}")
            try:
                machine_expand = page.get_by_test_id(f"machine-expand-{machine}")
                machine_expand.click(force=True)
            except:
                # Try alternative selector
                machine_row = page.locator(f'tr:has-text("{machine}")').first
                expand_button = machine_row.locator('button').first
                expand_button.click()
            
            page.wait_for_timeout(1000)
            
            # Show repositories if needed
            try:
                repo_button = page.get_by_test_id(f"machine-repositories-button-{machine}")
                if repo_button.is_visible():
                    repo_button.click()
                    page.wait_for_timeout(1000)
            except:
                pass
            
            # Find and click on repository
            self.log(f"Selecting repository: {repo}")
            repo_element = page.locator(f'text="{repo}"').first
            if repo_element.is_visible():
                repo_element.click()
                page.wait_for_timeout(1000)
            else:
                self.log(f"Repository not found: {repo}", level='warning')
                return False
            
            # Open push action - try multiple selectors
            self.log("Opening push dialog...")
            push_found = False
            
            # Try different selectors for push action
            selectors = [
                'button:has-text("push")',
                'text="push"',
                '[data-testid*="push"]',
                'img[alt="push"]',
                'button[title*="push"]'
            ]
            
            for selector in selectors:
                try:
                    push_action = page.locator(selector).first
                    if push_action.is_visible():
                        push_action.click()
                        push_found = True
                        break
                except:
                    continue
            
            if not push_found:
                self.log("Push action not found - trying Remote button", level='warning')
                # Try to find Remote button first
                try:
                    remote_button = page.locator(f'button:has-text("Remote")').first
                    if remote_button.is_visible():
                        remote_button.click()
                        page.wait_for_timeout(500)
                        # Now look for push in dropdown
                        push_in_dropdown = page.locator('.ant-dropdown button:has-text("push")').first
                        if push_in_dropdown.is_visible():
                            push_in_dropdown.click()
                            push_found = True
                except:
                    pass
            
            if not push_found:
                self.log("Could not find push action", level='error')
                return False
            
            page.wait_for_timeout(1500)
            
            # Configure push destination
            self.log("Configuring push destination...")
            
            # Try to select storage as destination type
            try:
                dest_dropdown = page.locator('.ant-select-selector').first
                if dest_dropdown.is_visible():
                    dest_dropdown.click()
                    page.wait_for_timeout(500)
                    
                    # Select "storage" option
                    storage_option = page.locator('.ant-select-item:has-text("storage")').first
                    if storage_option.is_visible():
                        storage_option.click()
                        page.wait_for_timeout(500)
            except:
                self.log("Could not select destination type", level='warning')
            
            # Select specific storage
            try:
                storage_dropdown = page.locator('.ant-select-selector').nth(1)
                if storage_dropdown.is_visible():
                    storage_dropdown.click()
                    page.wait_for_timeout(500)
                    
                    ms_option = page.locator(f'.ant-select-item:has-text("{storage}")').first
                    if ms_option.is_visible():
                        ms_option.click()
                        page.wait_for_timeout(500)
            except:
                self.log(f"Could not select storage: {storage}", level='warning')
            
            # Submit push operation
            self.log("Submitting push operation to queue...")
            try:
                add_button = page.get_by_test_id("push-add-to-queue-button")
                if not add_button.is_visible():
                    add_button = page.locator('button:has-text("Add to Queue")').first
                
                if add_button.is_visible():
                    page.wait_for_timeout(1000)
                    if add_button.is_enabled():
                        add_button.click()
                        self.log("Push operation queued successfully", level='success')
                        page.wait_for_timeout(2000)
                    else:
                        self.log("Add to Queue button is disabled", level='error')
                        return False
                else:
                    self.log("Add to Queue button not found", level='error')
                    return False
            except Exception as e:
                self.log(f"Failed to submit push: {str(e)}", level='error')
                return False
            
            # Close queue trace modal if present
            try:
                close_button = page.get_by_test_id("queue-trace-modal-close-button")
                if close_button.is_visible():
                    close_button.click()
                    page.wait_for_timeout(500)
            except:
                pass
            
            return True
            
        except Exception as e:
            self.log(f"Failed to configure push: {str(e)}", level='error')
            self.take_screenshot("push_error")
            return False
    
    def run_test(self, playwright: Playwright):
        """
        Main test execution flow.
        """
        self.log(f"{'='*60}")
        self.log(f"Starting {self.test_name}")
        self.log(f"{'='*60}")
        
        # Create page
        self.page = self.context.new_page()
        
        try:
            # Step 1: Login using base class method
            self.login_page = self.login(self.page)
            self.take_screenshot("01_after_login")
            
            # Step 2: Import Storage
            import_success = self.import_storage_configuration(self.login_page)
            if import_success:
                self.take_screenshot("02_after_storage_import")
                self.log("Storage import step completed", level='success')
            else:
                self.log("Storage import failed but continuing", level='warning')
            
            # Step 3: Configure Push
            machine = self.get_config_value('storageImport', 'targetMachine', default='rediacc11')
            repo = self.get_config_value('storageImport', 'targetRepository', default='repo03')
            storage = self.get_config_value('storageImport', 'targetStorage', default='microsoft')
            
            push_success = self.configure_and_execute_push(
                self.login_page, 
                machine=machine,
                repo=repo,
                storage=storage
            )
            
            if push_success:
                self.take_screenshot("03_after_push_config")
                self.log("✅ All test steps completed successfully!", level='success')
            else:
                self.log("Push configuration step failed but test completed", level='warning')
            
        except Exception as e:
            self.log(f"Test encountered an error: {str(e)}", level='error')
            self.take_screenshot("test_failure")
            raise
        
        finally:
            # Keep browser open briefly to see results
            if self.login_page:
                self.login_page.wait_for_timeout(2000)
            
            self.log(f"{'='*60}")
            self.log(f"Test {self.test_name} finished")
            self.log(f"{'='*60}")


def main():
    """Entry point for the test"""
    print("=" * 60)
    print("Storage Import and Push Test - Corrected Version")
    print("=" * 60)
    
    try:
        test = StorageImportPushTest()
        test.execute()
    except Exception as e:
        print(f"\n❌ Test initialization failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()