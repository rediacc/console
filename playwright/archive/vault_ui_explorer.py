#!/usr/bin/env python3
"""
Vault UI Explorer - Analyze vault configuration functionality
This script explores the UI to understand the actual implementation
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import sys

def run_exploration():
    """Main exploration function"""
    with sync_playwright() as playwright:
        # Launch browser
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            print("Starting Vault UI Exploration...")
            
            # Navigate to console
            print("1. Navigating to console...")
            page.goto("http://localhost:7322/console")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            
            # Take initial screenshot
            screenshot_dir = Path("/home/anl/monorepo/console/artifacts/screenshots")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_dir / "01_initial_page.png"))
            
            # Handle login
            current_url = page.url
            print(f"2. Current URL: {current_url}")
            
            if '/login' in current_url or current_url.endswith('/console/'):
                print("3. Performing login...")
                
                # Fill login form
                email_selectors = ['[data-testid="login-email-input"]', 'input[type="email"]', 'input[placeholder*="email" i]']
                password_selectors = ['[data-testid="login-password-input"]', 'input[type="password"]']
                submit_selectors = ['[data-testid="login-submit-button"]', 'button[type="submit"]', 'button:has-text("Sign In")']
                
                # Find and fill email
                email_input = None
                for selector in email_selectors:
                    try:
                        email_input = page.locator(selector).first
                        if email_input.is_visible():
                            break
                    except:
                        continue
                
                if email_input:
                    email_input.fill("admin@rediacc.io")
                else:
                    print("   Warning: Could not find email input")
                
                # Find and fill password
                password_input = None
                for selector in password_selectors:
                    try:
                        password_input = page.locator(selector).first
                        if password_input.is_visible():
                            break
                    except:
                        continue
                
                if password_input:
                    password_input.fill("admin")
                else:
                    print("   Warning: Could not find password input")
                
                # Find and click submit
                submit_button = None
                for selector in submit_selectors:
                    try:
                        submit_button = page.locator(selector).first
                        if submit_button.is_visible():
                            break
                    except:
                        continue
                
                if submit_button:
                    submit_button.click()
                    print("   Login submitted")
                else:
                    print("   Warning: Could not find submit button")
                
                # Wait for dashboard
                try:
                    page.wait_for_url("**/console/dashboard", timeout=10000)
                    print("   Login successful!")
                    page.screenshot(path=str(screenshot_dir / "02_after_login.png"))
                except:
                    print("   Warning: Did not reach dashboard")
            
            # Navigate to System page
            print("4. Navigating to System page...")
            try:
                # Try main navigation
                system_selectors = [
                    '[data-testid="main-nav-system"]',
                    'nav a:has-text("System")',
                    'a[href*="system"]'
                ]
                
                system_clicked = False
                for selector in system_selectors:
                    try:
                        system_link = page.locator(selector).first
                        if system_link.is_visible():
                            system_link.click()
                            system_clicked = True
                            print(f"   Clicked system link using: {selector}")
                            break
                    except:
                        continue
                
                if not system_clicked:
                    print("   Warning: Could not find System link")
                
                time.sleep(2)
                page.wait_for_load_state("networkidle")
                page.screenshot(path=str(screenshot_dir / "03_system_page.png"))
                
            except Exception as e:
                print(f"   Error navigating to System: {str(e)}")
            
            # Explore tabs on System page
            print("5. Exploring System page tabs...")
            try:
                # Look for tabs
                tab_selectors = [
                    '.ant-tabs-tab',
                    '[role="tab"]',
                    '.tab',
                    'button[role="tab"]'
                ]
                
                tabs_found = []
                for selector in tab_selectors:
                    try:
                        tabs = page.locator(selector).all()
                        for i, tab in enumerate(tabs):
                            if tab.is_visible():
                                tab_text = tab.inner_text().strip()
                                if tab_text:
                                    tabs_found.append({
                                        'selector': selector,
                                        'index': i,
                                        'text': tab_text,
                                        'data_testid': tab.get_attribute('data-testid') or 'N/A'
                                    })
                    except:
                        continue
                
                print(f"   Found tabs: {tabs_found}")
                
                # Click on Users tab if available
                users_tab = None
                for tab in tabs_found:
                    if 'user' in tab['text'].lower():
                        try:
                            users_tab = page.locator(tab['selector']).nth(tab['index'])
                            users_tab.click()
                            print(f"   Clicked on Users tab: {tab['text']}")
                            time.sleep(2)
                            page.screenshot(path=str(screenshot_dir / "04_users_tab.png"))
                            break
                        except:
                            continue
                
            except Exception as e:
                print(f"   Error exploring tabs: {str(e)}")
            
            # Look for vault configuration buttons
            print("6. Looking for vault configuration buttons...")
            try:
                # Look in table rows for vault buttons
                vault_selectors = [
                    '[data-testid*="vault"]',
                    'button:has-text("Vault")',
                    'button:has-text("Configure Vault")',
                    'button[title*="vault" i]',
                    'button[title*="Vault" i]',
                    '.ant-table button',
                    'td button'
                ]
                
                vault_buttons_found = []
                for selector in vault_selectors:
                    try:
                        buttons = page.locator(selector).all()
                        for i, button in enumerate(buttons):
                            if button.is_visible():
                                button_text = button.inner_text().strip()
                                button_title = button.get_attribute('title') or ''
                                button_testid = button.get_attribute('data-testid') or ''
                                
                                if any(keyword in (button_text + button_title + button_testid).lower() 
                                      for keyword in ['vault', 'configure', 'ssh', 'key']):
                                    vault_buttons_found.append({
                                        'selector': selector,
                                        'index': i,
                                        'text': button_text,
                                        'title': button_title,
                                        'testid': button_testid,
                                        'full_selector': f"{selector}:nth-child({i+1})" if selector == '.ant-table button' or selector == 'td button' else selector
                                    })
                    except Exception as e:
                        print(f"   Error with selector {selector}: {str(e)}")
                        continue
                
                print(f"   Found vault buttons: {vault_buttons_found}")
                
                # Try to click the first vault button found
                if vault_buttons_found:
                    first_button = vault_buttons_found[0]
                    try:
                        button = page.locator(first_button['selector']).nth(first_button['index'])
                        button.click()
                        print(f"   Clicked vault button: {first_button}")
                        time.sleep(2)
                        page.screenshot(path=str(screenshot_dir / "05_vault_button_clicked.png"))
                    except Exception as e:
                        print(f"   Error clicking vault button: {str(e)}")
                
            except Exception as e:
                print(f"   Error looking for vault buttons: {str(e)}")
            
            # Look for vault modal/dialog
            print("7. Exploring vault configuration dialog...")
            try:
                # Look for modal or dialog
                modal_selectors = [
                    '.ant-modal',
                    '[role="dialog"]',
                    '.modal',
                    '.dialog'
                ]
                
                modal_found = False
                for selector in modal_selectors:
                    try:
                        modal = page.locator(selector).first
                        if modal.is_visible():
                            print(f"   Found modal with selector: {selector}")
                            modal_found = True
                            
                            # Take screenshot of modal
                            page.screenshot(path=str(screenshot_dir / "06_vault_modal.png"))
                            
                            # Look for form fields inside modal
                            form_fields = []
                            field_selectors = [
                                'input',
                                'textarea',
                                'select',
                                '[contenteditable="true"]'
                            ]
                            
                            for field_selector in field_selectors:
                                try:
                                    fields = modal.locator(field_selector).all()
                                    for i, field in enumerate(fields):
                                        if field.is_visible():
                                            field_type = field.get_attribute('type') or 'text'
                                            field_name = field.get_attribute('name') or ''
                                            field_placeholder = field.get_attribute('placeholder') or ''
                                            field_testid = field.get_attribute('data-testid') or ''
                                            field_id = field.get_attribute('id') or ''
                                            
                                            form_fields.append({
                                                'selector': field_selector,
                                                'index': i,
                                                'type': field_type,
                                                'name': field_name,
                                                'placeholder': field_placeholder,
                                                'testid': field_testid,
                                                'id': field_id
                                            })
                                except:
                                    continue
                            
                            print(f"   Form fields found: {form_fields}")
                            
                            # Look for generate buttons
                            generate_buttons = []
                            generate_selectors = [
                                'button:has-text("Generate")',
                                'button[title*="generate" i]',
                                '[data-testid*="generate"]',
                                'button:has-text("Create")',
                                'button:has-text("New")'
                            ]
                            
                            for gen_selector in generate_selectors:
                                try:
                                    buttons = modal.locator(gen_selector).all()
                                    for i, button in enumerate(buttons):
                                        if button.is_visible():
                                            button_text = button.inner_text().strip()
                                            button_testid = button.get_attribute('data-testid') or ''
                                            button_title = button.get_attribute('title') or ''
                                            
                                            generate_buttons.append({
                                                'selector': gen_selector,
                                                'index': i,
                                                'text': button_text,
                                                'testid': button_testid,
                                                'title': button_title
                                            })
                                except:
                                    continue
                            
                            print(f"   Generate buttons found: {generate_buttons}")
                            
                            # Look for save/submit buttons
                            save_buttons = []
                            save_selectors = [
                                'button:has-text("Save")',
                                'button:has-text("OK")',
                                'button:has-text("Submit")',
                                'button.ant-btn-primary',
                                '[data-testid*="save"]',
                                'button[type="submit"]'
                            ]
                            
                            for save_selector in save_selectors:
                                try:
                                    buttons = modal.locator(save_selector).all()
                                    for i, button in enumerate(buttons):
                                        if button.is_visible():
                                            button_text = button.inner_text().strip()
                                            button_testid = button.get_attribute('data-testid') or ''
                                            button_class = button.get_attribute('class') or ''
                                            
                                            save_buttons.append({
                                                'selector': save_selector,
                                                'index': i,
                                                'text': button_text,
                                                'testid': button_testid,
                                                'class': button_class
                                            })
                                except:
                                    continue
                            
                            print(f"   Save buttons found: {save_buttons}")
                            
                            break
                    except:
                        continue
                
                if not modal_found:
                    print("   Warning: No vault modal found")
                
            except Exception as e:
                print(f"   Error exploring vault dialog: {str(e)}")
            
            # Try to generate SSH key if possible
            print("8. Attempting SSH key generation...")
            try:
                # Look for SSH key specific elements
                ssh_elements = []
                ssh_selectors = [
                    ':has-text("SSH")',
                    ':has-text("Private Key")',
                    ':has-text("PUBLIC_KEY")',
                    ':has-text("PRIVATE_KEY")',
                    '[data-testid*="SSH"]',
                    '[data-testid*="PRIVATE_KEY"]'
                ]
                
                for ssh_selector in ssh_selectors:
                    try:
                        elements = page.locator(ssh_selector).all()
                        for i, element in enumerate(elements):
                            if element.is_visible():
                                element_text = element.inner_text().strip()
                                element_testid = element.get_attribute('data-testid') or ''
                                
                                ssh_elements.append({
                                    'selector': ssh_selector,
                                    'index': i,
                                    'text': element_text,
                                    'testid': element_testid
                                })
                    except:
                        continue
                
                print(f"   SSH elements found: {ssh_elements}")
                
                # Try to click generate button for SSH key
                if ssh_elements:
                    # Look for generate button near SSH elements
                    for ssh_element in ssh_elements:
                        if 'PRIVATE_KEY' in ssh_element['text'] or 'SSH' in ssh_element['text']:
                            try:
                                # Look for nearby generate button
                                parent = page.locator(ssh_element['selector']).nth(ssh_element['index']).locator('..')
                                generate_btn = parent.locator('button:has-text("Generate")').first
                                if generate_btn.is_visible():
                                    generate_btn.click()
                                    print(f"   Clicked generate button for SSH key")
                                    time.sleep(2)
                                    page.screenshot(path=str(screenshot_dir / "07_ssh_generate_clicked.png"))
                                    break
                            except:
                                continue
                
            except Exception as e:
                print(f"   Error attempting SSH key generation: {str(e)}")
            
            # Final screenshot
            print("9. Taking final screenshots...")
            page.screenshot(path=str(screenshot_dir / "08_final_state.png"))
            
            print("\n=== EXPLORATION SUMMARY ===")
            print("Check the screenshots in /home/anl/monorepo/console/artifacts/screenshots/")
            print("- Look for vault-related buttons and their test IDs")
            print("- Check modal structure and form fields")
            print("- Review SSH key generation process")
            print("- Note success messages and indicators")
            
            # Keep browser open for manual inspection
            print("\n10. Browser will stay open for 30 seconds for manual inspection...")
            time.sleep(30)
            
        except Exception as e:
            print(f"\nError during exploration: {str(e)}")
            page.screenshot(path=str(screenshot_dir / "error_exploration.png"))
            raise
        
        finally:
            context.close()
            browser.close()
            print("Browser closed.")

if __name__ == "__main__":
    run_exploration()