#!/usr/bin/env python3
"""
Detailed Vault UI Explorer - Focus on SSH key generation and full vault form
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

def run_detailed_exploration():
    """Detailed exploration of vault configuration"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            print("=== DETAILED VAULT EXPLORATION ===")
            
            # Navigate and login
            print("1. Navigating and logging in...")
            page.goto("http://localhost:7322/console")
            page.wait_for_load_state("domcontentloaded")
            
            if '/login' in page.url:
                page.locator('input[type="email"]').fill("admin@rediacc.io")
                page.locator('input[type="password"]').fill("admin")
                page.locator('button[type="submit"]').click()
                page.wait_for_url("**/console/dashboard", timeout=10000)
            
            # Navigate to System
            page.get_by_test_id("main-nav-system").click()
            time.sleep(2)
            
            # Click company vault button
            print("2. Opening Company vault...")
            company_vault_btn = page.get_by_test_id("system-company-vault-button")
            company_vault_btn.click()
            time.sleep(2)
            
            screenshot_dir = Path("/home/anl/monorepo/console/artifacts/screenshots")
            page.screenshot(path=str(screenshot_dir / "detailed_01_company_vault_modal.png"))
            
            # Scroll down in the modal to see all fields
            print("3. Exploring all vault fields...")
            modal = page.locator('.ant-modal')
            
            # Scroll to see all fields
            modal.evaluate("element => element.scrollTo(0, element.scrollHeight)")
            time.sleep(1)
            page.screenshot(path=str(screenshot_dir / "detailed_02_vault_scrolled.png"))
            
            # Look for Optional Fields section and expand if needed
            try:
                optional_fields = page.locator('[data-testid="vault-editor-panel-optional"]')
                if optional_fields.is_visible():
                    print("   Found optional fields section")
                    # Try to expand if collapsed
                    expand_button = optional_fields.locator('.ant-collapse-header').first
                    if expand_button.is_visible():
                        expand_button.click()
                        time.sleep(1)
                        print("   Expanded optional fields")
            except:
                pass
            
            # Take screenshot after expansion
            page.screenshot(path=str(screenshot_dir / "detailed_03_optional_fields_expanded.png"))
            
            # Focus on SSH key generation
            print("4. Exploring SSH key generation...")
            
            # Look for SSH Private Key field
            ssh_private_key_field = page.get_by_test_id("vault-editor-field-SSH_PRIVATE_KEY")
            if ssh_private_key_field.is_visible():
                print("   Found SSH Private Key field")
                
                # Look for generate button next to SSH Private Key
                generate_private_key_btn = page.get_by_test_id("vault-editor-generate-SSH_PRIVATE_KEY")
                if generate_private_key_btn.is_visible():
                    print("   Found Generate button for SSH Private Key")
                    
                    # Click generate button
                    generate_private_key_btn.click()
                    time.sleep(2)
                    page.screenshot(path=str(screenshot_dir / "detailed_04_ssh_generate_dialog.png"))
                    
                    # Look for the generate dialog elements
                    try:
                        # Look for actual generate button in popup
                        generate_btn = page.get_by_test_id("vault-editor-generate-button")
                        if generate_btn.is_visible():
                            print("   Found Generate button in dialog")
                            generate_btn.click()
                            time.sleep(2)
                            page.screenshot(path=str(screenshot_dir / "detailed_05_ssh_generated.png"))
                            
                            # Look for apply button
                            apply_btn = page.get_by_test_id("vault-editor-apply-generated")
                            if apply_btn.is_visible():
                                print("   Found Apply Generated button")
                                apply_btn.click()
                                time.sleep(1)
                                page.screenshot(path=str(screenshot_dir / "detailed_06_ssh_applied.png"))
                                print("   SSH key generated and applied!")
                    except Exception as e:
                        print(f"   Error in generate dialog: {str(e)}")
            
            # Check SSH Public Key field
            ssh_public_key_field = page.get_by_test_id("vault-editor-field-SSH_PUBLIC_KEY")
            if ssh_public_key_field.is_visible():
                print("   Found SSH Public Key field")
                
                generate_public_key_btn = page.get_by_test_id("vault-editor-generate-SSH_PUBLIC_KEY")
                if generate_public_key_btn.is_visible():
                    print("   Found Generate button for SSH Public Key")
            
            # Look for save button and save configuration
            print("5. Saving vault configuration...")
            save_btn = page.get_by_test_id("vault-modal-save-button")
            if save_btn.is_visible():
                print("   Found Save button")
                save_btn.click()
                time.sleep(2)
                page.screenshot(path=str(screenshot_dir / "detailed_07_vault_saved.png"))
                print("   Vault configuration saved!")
                
                # Look for success message
                try:
                    # Wait for success notification or modal close
                    page.wait_for_selector('.ant-modal', state='hidden', timeout=5000)
                    print("   Modal closed successfully")
                except:
                    print("   Modal may still be open")
            
            # Try User vault as well
            print("6. Testing User vault...")
            try:
                user_vault_btn = page.get_by_test_id("system-user-vault-button")
                if user_vault_btn.is_visible():
                    user_vault_btn.click()
                    time.sleep(2)
                    page.screenshot(path=str(screenshot_dir / "detailed_08_user_vault_modal.png"))
                    
                    # Close user vault modal
                    close_btn = page.locator('.ant-modal .ant-modal-close')
                    if close_btn.is_visible():
                        close_btn.click()
                        time.sleep(1)
            except Exception as e:
                print(f"   Error with user vault: {str(e)}")
            
            # Final screenshot
            page.screenshot(path=str(screenshot_dir / "detailed_09_final_state.png"))
            
            print("\n=== DETAILED EXPLORATION COMPLETE ===")
            print("Key findings:")
            print("- Company vault button: system-company-vault-button")
            print("- User vault button: system-user-vault-button") 
            print("- SSH Private Key field: vault-editor-field-SSH_PRIVATE_KEY")
            print("- SSH Private Key generate: vault-editor-generate-SSH_PRIVATE_KEY")
            print("- SSH Public Key field: vault-editor-field-SSH_PUBLIC_KEY")
            print("- SSH Public Key generate: vault-editor-generate-SSH_PUBLIC_KEY")
            print("- Generate dialog button: vault-editor-generate-button")
            print("- Apply generated button: vault-editor-apply-generated")
            print("- Save button: vault-modal-save-button")
            
            # Keep browser open for manual inspection
            time.sleep(10)
            
        except Exception as e:
            print(f"\nError during detailed exploration: {str(e)}")
            page.screenshot(path=str(screenshot_dir / "detailed_error.png"))
            raise
        
        finally:
            context.close()
            browser.close()
            print("Browser closed.")

if __name__ == "__main__":
    run_detailed_exploration()