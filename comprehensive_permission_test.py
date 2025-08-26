#!/usr/bin/env python3
"""
Comprehensive Permission Group Creation Documentation Test
"""

import time
from playwright.sync_api import sync_playwright

def run_comprehensive_test():
    """Run comprehensive test to document permission group creation"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(10000)
        
        try:
            print("=== PERMISSION GROUP CREATION DOCUMENTATION TEST ===")
            print()
            
            # Step 1: Navigate and Login
            print("STEP 1: Navigate to Console and Login")
            page.goto("http://localhost:7322/console")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            
            # Login with admin credentials
            page.fill('input[placeholder*="email"]', 'admin@rediacc.io')
            page.fill('input[placeholder*="password"]', 'admin')
            page.click('button:has-text("Sign In")')
            page.wait_for_url("**/console/dashboard")
            print("✓ Successfully logged in as admin@rediacc.io")
            print()
            
            # Step 2: Navigate to System
            print("STEP 2: Navigate to System Page")
            page.click('text=System')
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            page.screenshot(path="step1_system_page_simple_mode.png", full_page=True)
            print("✓ Navigated to System page (Simple mode by default)")
            print()
            
            # Step 3: Switch to Expert Mode
            print("STEP 3: Switch to Expert Mode")
            print("- In Simple mode, only Users and Teams tabs are visible")
            page.click('label:has-text("Expert")')
            time.sleep(1)
            page.screenshot(path="step2_system_page_expert_mode.png", full_page=True)
            print("✓ Switched to Expert mode")
            print("- Now showing additional tabs: Permissions, User Sessions")
            print("- Additional system sections: Regions & Infrastructure, Bridges, Danger Zone")
            print()
            
            # Step 4: Access Permissions Tab
            print("STEP 4: Access Permissions Tab")
            page.click('text=Permissions')
            time.sleep(1)
            page.screenshot(path="step3_permissions_tab_overview.png", full_page=True)
            
            # Document existing permission groups
            permission_groups = page.locator('.ant-tag').all_text_contents()
            print("✓ Accessed Permissions tab")
            print("- Current permission groups visible:")
            for group in permission_groups:
                if group.strip():
                    print(f"  • {group}")
            print()
            
            # Step 5: Create Permission Group
            print("STEP 5: Create New Permission Group")
            
            # Look for the create button - it should be in the Permissions section specifically
            create_button = None
            
            # First, let's see if we need to scroll or look in a specific area
            # The permissions section should have its own create button
            try:
                # Try to find create button near the permissions content
                create_selectors = [
                    'button[data-testid="system-create-permission-group-button"]',
                    '.ant-tabs-tabpane-active button:has-text("Create")',
                    '.ant-tabs-tabpane-active button:has([aria-label="plus"])',
                    '.ant-tabs-tabpane-active [aria-label="plus"]'
                ]
                
                for selector in create_selectors:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible():
                            create_button = btn
                            print(f"✓ Found create button using: {selector}")
                            break
                    except:
                        continue
                
                if not create_button:
                    # If no specific create button found, document what's available
                    print("- Searching for permission group creation button...")
                    all_buttons = page.locator('button').all()
                    print(f"- Found {len(all_buttons)} buttons on page")
                    
                    # Look for any create-type buttons
                    for btn in all_buttons:
                        try:
                            if btn.is_visible():
                                text = btn.text_content()
                                if text and ('create' in text.lower() or '+' in text or 'add' in text.lower()):
                                    print(f"  • Button: '{text}'")
                        except:
                            continue
                    
                    # Try a more general approach
                    create_button = page.locator('button:has-text("Create")').first
                    if not create_button.is_visible():
                        print("- No Create Permission Group button found in current view")
                        print("- This might require a different UI interaction or permission level")
                        return
                
                # Click the create button
                create_button.click()
                time.sleep(1)
                page.screenshot(path="step4_create_permission_dialog.png", full_page=True)
                print("✓ Opened Create Permission Group dialog")
                print()
                
                # Step 6: Fill Group Details
                print("STEP 6: Fill Permission Group Details")
                
                # Find and fill the group name
                name_input = page.locator('.ant-modal input[type="text"]').first
                group_name = "TestPermissionGroup01"
                name_input.fill(group_name)
                time.sleep(1)
                page.screenshot(path="step5_group_name_filled.png", full_page=True)
                print(f"✓ Entered group name: {group_name}")
                print()
                
                # Step 7: Submit Creation
                print("STEP 7: Submit Permission Group Creation")
                submit_button = page.locator('.ant-modal button:has-text("OK")').first
                submit_button.click()
                time.sleep(3)
                page.screenshot(path="step6_after_creation.png", full_page=True)
                print("✓ Submitted permission group creation")
                
                # Check for success indication
                success_elements = page.locator('.ant-message, .ant-notification').all()
                if success_elements:
                    print("✓ Success notification displayed")
                
                # Verify the group appears in the permissions list
                time.sleep(1)
                updated_permission_groups = page.locator('.ant-tag').all_text_contents()
                if group_name in str(updated_permission_groups):
                    print(f"✓ Permission group '{group_name}' appears in the permissions list")
                else:
                    print(f"- Permission group '{group_name}' may have been created but not immediately visible")
                print()
                
            except Exception as e:
                print(f"Error during permission group creation: {e}")
                page.screenshot(path="step_error_permission_creation.png", full_page=True)
                print("- Error screenshot saved: step_error_permission_creation.png")
            
            print("=== TEST COMPLETED ===")
            print()
            print("Screenshots saved:")
            print("- step1_system_page_simple_mode.png - System page in Simple mode")
            print("- step2_system_page_expert_mode.png - System page in Expert mode") 
            print("- step3_permissions_tab_overview.png - Permissions tab overview")
            print("- step4_create_permission_dialog.png - Create permission group dialog")
            print("- step5_group_name_filled.png - Group name filled")
            print("- step6_after_creation.png - After creation completed")
            print()
            
            print("FINDINGS:")
            print("1. Login: Use placeholder-based selectors for email/password inputs")
            print("2. System Navigation: Click 'System' in left sidebar")
            print("3. Mode Switch: Must switch to Expert mode to see Permissions tab")
            print("4. Permissions Tab: Click 'Permissions' tab after Expert mode enabled")
            print("5. Creation: Use specific permission group create button")
            print("6. Form: Simple dialog with group name input")
            print("7. Submission: Click 'OK' to create the permission group")
            
        except Exception as e:
            print(f"Unexpected error: {e}")
            page.screenshot(path="comprehensive_test_error.png", full_page=True)
        
        finally:
            time.sleep(3)
            browser.close()

if __name__ == "__main__":
    run_comprehensive_test()