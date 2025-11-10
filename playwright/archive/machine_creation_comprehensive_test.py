#!/usr/bin/env python3
"""
Comprehensive Machine Creation Test with Enhanced Message Capture
This script performs a detailed machine creation test with comprehensive monitoring
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

def generate_unique_machine_name():
    """Generate a unique machine name with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"rediacc21_{timestamp}"

def capture_all_messages(page, step_name=""):
    """Capture all visible messages, toasts, and notifications"""
    messages = []
    
    # Various selectors for different types of messages
    selectors = [
        ".ant-message",
        ".ant-notification",
        ".ant-notification-notice",
        ".ant-modal-confirm-content",
        "[role='alert']",
        ".toast-success",
        ".toast-error", 
        ".toast-info",
        ".notification-success",
        ".notification-error",
        "text=/success/i",
        "text=/error/i",
        "text=/created/i",
        "text=/failed/i",
        "text=/SSH connection/i",
        "text=/Task Completed/i",
        "text=/Machine.*created/i",
        "[data-testid*='success']",
        "[data-testid*='error']",
        "[data-testid*='message']",
        "[class*='success']",
        "[class*='error']",
        "[class*='message']",
        "[class*='notification']",
        "[class*='alert']"
    ]
    
    for selector in selectors:
        try:
            elements = page.locator(selector).all()
            for element in elements:
                if element.is_visible():
                    text = element.text_content()
                    if text and text.strip() and len(text.strip()) > 0:
                        messages.append({
                            'selector': selector,
                            'text': text.strip(),
                            'step': step_name,
                            'timestamp': datetime.now().isoformat()
                        })
        except Exception as e:
            continue
    
    # Also capture page title and URL for context
    try:
        messages.append({
            'selector': 'page_info',
            'text': f"URL: {page.url}, Title: {page.title()}",
            'step': step_name,
            'timestamp': datetime.now().isoformat()
        })
    except:
        pass
    
    return messages

def wait_and_capture_messages(page, wait_time=2000, step_name=""):
    """Wait for a period and capture any messages that appear"""
    page.wait_for_timeout(wait_time)
    return capture_all_messages(page, step_name)

def take_screenshot(page, filename_suffix, base_path="./playwright/artifacts/screenshots"):
    """Take a screenshot with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_dir = Path(base_path)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshot_dir / f"{filename_suffix}_{timestamp}.png"
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"📸 Screenshot saved: {screenshot_path}")
    return str(screenshot_path)

def run_comprehensive_machine_creation_test():
    """Run the comprehensive machine creation test"""
    
    print("🚀 Starting Comprehensive Machine Creation Test")
    print("=" * 60)
    
    all_messages = []
    screenshots = []
    
    with sync_playwright() as playwright:
        # Launch browser (non-headless for observation)
        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=1000  # Slow down for better observation
        )
        
        context = browser.new_context(
            viewport={'width': 1440, 'height': 900}
        )
        
        page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # Step 1: Navigate to login page
            print("\n📍 Step 1: Navigating to login page...")
            page.goto("http://localhost:7322/console/login")
            messages = wait_and_capture_messages(page, 3000, "navigate_to_login")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "01_login_page"))
            
            # Step 2: Fill login form
            print("\n📍 Step 2: Filling login credentials...")
            page.get_by_test_id("login-email-input").fill("admin@rediacc.io")
            page.get_by_test_id("login-password-input").fill("admin")
            messages = wait_and_capture_messages(page, 1000, "login_form_filled")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "login_filled"))
            
            # Step 3: Submit login
            print("\n📍 Step 3: Submitting login...")
            page.get_by_test_id("login-submit-button").click()
            page.wait_for_url("**/console/dashboard", timeout=15000)
            messages = wait_and_capture_messages(page, 3000, "login_successful")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "03_dashboard_loaded"))
            print("✅ Login successful - Dashboard loaded")
            
            # Step 4: Navigate to Resources
            print("\n📍 Step 4: Navigating to Resources...")
            page.get_by_test_id("main-nav-machines").click()
            page.wait_for_selector('[data-testid="resources-create-machine-button"]', state='visible')
            messages = wait_and_capture_messages(page, 2000, "resources_page_loaded")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "04_resources_page"))
            print("✅ Resources page loaded")
            
            # Step 5: Open Create Machine modal
            print("\n📍 Step 5: Opening Create Machine modal...")
            page.get_by_test_id("resources-create-machine-button").click()
            page.wait_for_selector('[data-testid="resource-modal-field-machineName-input"]', state='visible')
            messages = wait_and_capture_messages(page, 2000, "modal_opened")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "05_create_machine_modal"))
            print("✅ Create Machine modal opened")
            
            # Step 6: Fill machine name
            machine_name = generate_unique_machine_name()
            print(f"\n📍 Step 6: Filling machine name: {machine_name}")
            page.get_by_test_id("resource-modal-field-machineName-input").fill(machine_name)
            messages = wait_and_capture_messages(page, 1000, "machine_name_filled")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "06_machine_name_filled"))
            
            # Step 7: Expand Required Fields if needed
            print("\n📍 Step 7: Ensuring Required Fields are expanded...")
            
            # Look for the collapsed Required Fields section by finding the right arrow icon
            # The structure is: div containing both the arrow and "Required Fields" text
            try:
                # Try multiple selectors to find and click the Required Fields header
                selectors_to_try = [
                    "div:has-text('Required Fields'):has([data-icon='right'])",  # Div with text and right arrow
                    ".ant-collapse-header:has-text('Required Fields')",          # Ant collapse header
                    "[role='button']:has-text('Required Fields')",              # Button role
                    "div:has-text('Required Fields')",                          # Any div with the text
                    "text=Required Fields"                                       # Simple text selector
                ]
                
                expanded = False
                for selector in selectors_to_try:
                    try:
                        element = page.locator(selector).first()
                        if element.count() > 0:
                            print(f"🔧 Found Required Fields with selector: {selector}")
                            element.click()
                            page.wait_for_timeout(1500)  # Wait a bit longer for expansion
                            
                            # Check if the IP field is now visible
                            ip_field = page.get_by_test_id("vault-editor-field-ip")
                            try:
                                ip_field.wait_for(state='visible', timeout=2000)
                                print("✅ Required Fields section expanded - IP field is now visible")
                                expanded = True
                                break
                            except:
                                print(f"⚠️  IP field still not visible after clicking {selector}")
                                continue
                    except Exception as e:
                        continue
                
                if not expanded:
                    print("⚠️  Could not expand Required Fields, but continuing...")
                    
            except Exception as e:
                print(f"⚠️  Error expanding Required Fields: {e}")
                print("Continuing with test...")
            
            messages = wait_and_capture_messages(page, 2000, "required_fields_expanded")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "07_required_fields_expanded"))
            
            # Step 8: Fill IP address
            print("\n📍 Step 8: Filling IP address...")
            ip_field = page.get_by_test_id("vault-editor-field-ip")
            ip_field.wait_for(state='visible', timeout=10000)
            ip_field.fill("192.168.111.21")
            messages = wait_and_capture_messages(page, 1000, "ip_filled")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "08_ip_filled"))
            print("✅ IP address filled: 192.168.111.21")
            
            # Step 9: Fill username
            print("\n📍 Step 9: Filling username...")
            user_field = page.get_by_test_id("vault-editor-field-user")
            user_field.wait_for(state='visible', timeout=10000)
            user_field.fill("anl")
            messages = wait_and_capture_messages(page, 1000, "user_filled")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "09_user_filled"))
            print("✅ Username filled: anl")
            
            # Step 10: Set vault status to configured
            print("\n📍 Step 10: Setting vault configuration...")
            configured_elements = page.locator("div").filter(has_text=re.compile(r"^Configured$"))
            if configured_elements.count() > 0:
                configured_elements.nth(1).click()
                page.wait_for_timeout(1000)
            
            messages = wait_and_capture_messages(page, 2000, "vault_configured")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "10_vault_configured"))
            
            # Step 11: Test SSH connection
            print("\n📍 Step 11: Testing SSH connection...")
            test_button = page.get_by_test_id("vault-editor-test-connection")
            test_button.wait_for(state='visible', timeout=10000)
            test_button.click()
            
            # Wait for connection test and monitor for success
            connection_test_success = False
            for i in range(20):  # Wait up to 20 seconds
                messages = capture_all_messages(page, f"connection_test_attempt_{i+1}")
                all_messages.extend(messages)
                
                # Check for success indicators
                success_patterns = [
                    "SSH connection successful",
                    "Connection successful",
                    "Test successful",
                    "✓"
                ]
                
                for msg in messages:
                    for pattern in success_patterns:
                        if pattern.lower() in msg['text'].lower():
                            connection_test_success = True
                            print(f"✅ SSH connection test successful: {msg['text']}")
                            break
                    if connection_test_success:
                        break
                
                if connection_test_success:
                    break
                    
                page.wait_for_timeout(1000)
            
            screenshots.append(take_screenshot(page, "11_connection_test_completed"))
            
            if not connection_test_success:
                print("⚠️  SSH connection test status unclear, continuing...")
            
            # Step 12: Wait for OK button to be enabled
            print("\n📍 Step 12: Waiting for OK button to be enabled...")
            ok_button = page.get_by_test_id("resource-modal-ok-button")
            ok_button.wait_for(state='visible', timeout=10000)
            
            # Wait a bit more to ensure button is enabled
            page.wait_for_timeout(3000)
            messages = wait_and_capture_messages(page, 1000, "pre_creation")
            all_messages.extend(messages)
            screenshots.append(take_screenshot(page, "12_ready_to_create"))
            
            # Step 13: Create machine
            print("\n📍 Step 13: Creating machine...")
            ok_button.click()
            
            # Monitor for creation messages
            creation_success = False
            for i in range(30):  # Wait up to 30 seconds for creation
                messages = capture_all_messages(page, f"creation_attempt_{i+1}")
                all_messages.extend(messages)
                
                # Check for success indicators
                success_patterns = [
                    "Machine created successfully",
                    "Machine.*created successfully",
                    "created successfully",
                    "Setup has been queued",
                    "Task Completed Successfully"
                ]
                
                for msg in messages:
                    for pattern in success_patterns:
                        if re.search(pattern, msg['text'], re.IGNORECASE):
                            creation_success = True
                            print(f"✅ Machine creation success: {msg['text']}")
                            break
                    if creation_success:
                        break
                
                if creation_success:
                    break
                    
                page.wait_for_timeout(1000)
            
            screenshots.append(take_screenshot(page, "13_after_creation_attempt"))
            
            # Step 14: Handle any queue trace dialog
            print("\n📍 Step 14: Handling queue trace dialog if present...")
            try:
                queue_trace_close = page.get_by_test_id("queue-trace-close-button")
                if queue_trace_close.count() > 0:
                    print("📋 Queue trace dialog detected, monitoring...")
                    # Wait to see queue progress
                    page.wait_for_timeout(5000)
                    
                    # Capture queue trace messages
                    messages = capture_all_messages(page, "queue_trace_monitoring")
                    all_messages.extend(messages)
                    screenshots.append(take_screenshot(page, "14_queue_trace_dialog"))
                    
                    # Check for completion
                    for msg in messages:
                        if "completed" in msg['text'].lower() or "successful" in msg['text'].lower():
                            print(f"✅ Queue task completed: {msg['text']}")
                    
                    # Close the dialog
                    queue_trace_close.click()
                    page.wait_for_timeout(1000)
            except:
                print("ℹ️  No queue trace dialog detected")
            
            # Step 15: Final state capture
            print("\n📍 Step 15: Capturing final state...")
            final_messages = wait_and_capture_messages(page, 3000, "final_state")
            all_messages.extend(final_messages)
            screenshots.append(take_screenshot(page, "15_final_state"))
            
            print("\n" + "=" * 60)
            print("🎉 TEST COMPLETED!")
            print(f"📋 Machine Name: {machine_name}")
            print(f"🖼️  Screenshots taken: {len(screenshots)}")
            print(f"📨 Messages captured: {len(all_messages)}")
            
            if creation_success:
                print("✅ Machine creation appears to have succeeded")
            else:
                print("⚠️  Machine creation status unclear")
                
        except Exception as e:
            print(f"\n❌ Error during test: {str(e)}")
            screenshots.append(take_screenshot(page, "error_state"))
            messages = capture_all_messages(page, "error_state")
            all_messages.extend(messages)
            raise
        finally:
            # Clean up
            context.close()
            browser.close()
    
    # Save comprehensive results
    results = {
        'test_completed_at': datetime.now().isoformat(),
        'machine_name': machine_name if 'machine_name' in locals() else None,
        'screenshots': screenshots,
        'total_messages': len(all_messages),
        'messages': all_messages,
        'success': creation_success if 'creation_success' in locals() else False
    }
    
    results_file = Path("./machine_creation_test_results.json")
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: {results_file}")
    
    # Print summary of messages
    print("\n📝 MESSAGE SUMMARY:")
    print("-" * 40)
    unique_messages = set()
    for msg in all_messages:
        if msg['text'] not in unique_messages and len(msg['text'].strip()) > 3:
            unique_messages.add(msg['text'])
            print(f"• {msg['step']}: {msg['text'][:100]}")
    
    return results

if __name__ == "__main__":
    try:
        results = run_comprehensive_machine_creation_test()
        sys.exit(0 if results['success'] else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        sys.exit(1)