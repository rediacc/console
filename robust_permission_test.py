#!/usr/bin/env python3
"""
Robust Permission Group Creation Test
"""

import asyncio
import time
from playwright.sync_api import sync_playwright, expect

def run_test():
    """Run the test to capture permission creation"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(10000)
        
        try:
            print("1. Navigating to console...")
            page.goto("http://localhost:7322/console")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)
            
            # Take screenshot of initial page
            page.screenshot(path="00_initial_page.png", full_page=True)
            print("   Initial page screenshot saved")
            
            # Check current URL
            current_url = page.url
            print(f"   Current URL: {current_url}")
            
            # Look for login form or dashboard
            try:
                # Check if already on dashboard
                if 'dashboard' in current_url:
                    print("2. Already on dashboard")
                else:
                    # Look for email and password placeholders
                    email_input = page.locator('input[placeholder*="email"]').first
                    password_input = page.locator('input[placeholder*="password"]').first
                    
                    if email_input.is_visible() and password_input.is_visible():
                        print("2. Login form found, logging in...")
                        email_input.fill('admin@rediacc.io')
                        password_input.fill('admin')
                        page.click('button:has-text("Sign In")')
                        page.wait_for_url("**/console/dashboard", timeout=10000)
                        print("   Login successful!")
                    else:
                        print("   Can't find login form inputs")
                        return
            except Exception as e:
                print(f"   Login error: {e}")
                page.screenshot(path="login_error.png", full_page=True)
                return
            
            print("3. Navigating to System...")
            try:
                system_link = page.locator('text=System').first
                system_link.click()
                page.wait_for_load_state("networkidle")
                time.sleep(1)
                page.screenshot(path="01_system_page.png", full_page=True)
                print("   System page screenshot saved")
            except Exception as e:
                print(f"   System navigation error: {e}")
                page.screenshot(path="system_nav_error.png", full_page=True)
                return
            
            print("4. Checking interface mode...")
            try:
                expert_label = page.locator('label:has-text("Expert")').first
                if expert_label.is_visible():
                    print("   Switching to Expert mode...")
                    expert_label.click()
                    time.sleep(1)
                    page.screenshot(path="02_expert_mode.png", full_page=True)
                else:
                    print("   Expert mode selector not found, continuing...")
            except Exception as e:
                print(f"   Mode switch error: {e}")
            
            print("5. Accessing Permissions tab...")
            try:
                permissions_selectors = [
                    'text=Permissions',
                    '.ant-tabs-tab:has-text("Permissions")',
                    '[data-testid="system-tab-permissions"]'
                ]
                
                permissions_clicked = False
                for selector in permissions_selectors:
                    try:
                        permissions_tab = page.locator(selector).first
                        if permissions_tab.is_visible():
                            permissions_tab.click()
                            permissions_clicked = True
                            print(f"   Permissions tab clicked using: {selector}")
                            break
                    except:
                        continue
                
                if not permissions_clicked:
                    print("   Could not find Permissions tab")
                    page.screenshot(path="permissions_tab_error.png", full_page=True)
                    return
                
                time.sleep(1)
                page.screenshot(path="03_permissions_tab.png", full_page=True)
                print("   Permissions tab screenshot saved")
                
            except Exception as e:
                print(f"   Permissions tab error: {e}")
                page.screenshot(path="permissions_error.png", full_page=True)
                return
            
            print("6. Finding Create Permission Group button...")
            try:
                create_selectors = [
                    'button:has-text("+")',
                    'button.ant-btn:has([aria-label="plus"])',
                    '[aria-label="plus"]',
                    'button:has-text("Create")',
                    '[data-testid="system-create-permission-group-button"]',
                    'button:has-text("Add")',
                    'button:has-text("Create Permission Group")'
                ]
                
                create_clicked = False
                for selector in create_selectors:
                    try:
                        create_button = page.locator(selector).first
                        if create_button.is_visible():
                            create_button.click()
                            create_clicked = True
                            print(f"   Create button clicked using: {selector}")
                            break
                    except:
                        continue
                
                if not create_clicked:
                    print("   Could not find Create Permission Group button")
                    page.screenshot(path="create_button_error.png", full_page=True)
                    return
                
                time.sleep(1)
                page.screenshot(path="04_create_modal.png", full_page=True)
                print("   Create modal screenshot saved")
                
            except Exception as e:
                print(f"   Create button error: {e}")
                page.screenshot(path="create_error.png", full_page=True)
                return
            
            print("7. Filling group name...")
            try:
                name_selectors = [
                    '.ant-modal input[type="text"]',
                    '[data-testid="system-permission-group-name-input"]',
                    '.ant-modal input:not([type="password"])',
                    '.ant-form-item input'
                ]
                
                name_filled = False
                for selector in name_selectors:
                    try:
                        name_input = page.locator(selector).first
                        if name_input.is_visible():
                            name_input.fill('TestGroup04')
                            name_filled = True
                            print(f"   Group name filled using: {selector}")
                            break
                    except:
                        continue
                
                if not name_filled:
                    print("   Could not find group name input")
                    page.screenshot(path="name_input_error.png", full_page=True)
                    return
                
                time.sleep(1)
                page.screenshot(path="05_group_name_filled.png", full_page=True)
                print("   Group name filled screenshot saved")
                
            except Exception as e:
                print(f"   Name input error: {e}")
                page.screenshot(path="name_error.png", full_page=True)
                return
            
            print("8. Submitting the form...")
            try:
                submit_selectors = [
                    '.ant-modal button:has-text("OK")',
                    '[data-testid="modal-create-permission-group-ok"]',
                    '.ant-modal button.ant-btn-primary',
                    '.ant-modal button[type="submit"]'
                ]
                
                submit_clicked = False
                for selector in submit_selectors:
                    try:
                        submit_button = page.locator(selector).first
                        if submit_button.is_visible():
                            submit_button.click()
                            submit_clicked = True
                            print(f"   Submit button clicked using: {selector}")
                            break
                    except:
                        continue
                
                if not submit_clicked:
                    print("   Could not find submit button")
                    page.screenshot(path="submit_button_error.png", full_page=True)
                    return
                
                time.sleep(3)
                page.screenshot(path="06_after_creation.png", full_page=True)
                print("   After creation screenshot saved")
                
            except Exception as e:
                print(f"   Submit error: {e}")
                page.screenshot(path="submit_error.png", full_page=True)
                return
            
            print("Test completed successfully!")
            print("Screenshots saved:")
            print("  - 00_initial_page.png")
            print("  - 01_system_page.png") 
            print("  - 02_expert_mode.png")
            print("  - 03_permissions_tab.png")
            print("  - 04_create_modal.png")
            print("  - 05_group_name_filled.png")
            print("  - 06_after_creation.png")
            
        except Exception as e:
            print(f"Unexpected error: {e}")
            page.screenshot(path="unexpected_error.png", full_page=True)
        
        finally:
            time.sleep(3)
            browser.close()

if __name__ == "__main__":
    run_test()