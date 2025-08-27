#!/usr/bin/env python3

import json
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import Playwright, sync_playwright, expect

def run_bridge_test_with_console_capture():
    """Run bridge test and capture console messages"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, slow_mo=1000)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        
        console_messages = []
        
        def handle_console(msg):
            console_messages.append({
                'type': msg.type,
                'text': msg.text,
                'timestamp': datetime.now().isoformat()
            })
        
        page.on('console', handle_console)
        
        try:
            print("🚀 Starting Final Bridge Creation Test...")
            
            # Navigate and login
            print("📍 Step 1: Navigating to console...")
            page.goto("http://localhost:7322/console/login", timeout=10000)
            page.wait_for_load_state("networkidle", timeout=10000)
            
            # Skip encryption dialog if it appears
            try:
                skip_button = page.locator("button:has-text('Skip')").first
                if skip_button.is_visible(timeout=2000):
                    print("Skipping encryption dialog...")
                    skip_button.click()
                    page.wait_for_timeout(1000)
            except:
                print("No encryption dialog found")
            
            print("🔐 Step 2: Logging in...")
            page.fill('input[type="email"]', "admin@rediacc.io")
            page.fill('input[type="password"]', "admin") 
            page.click('button:has-text("Login")')
            page.wait_for_load_state("networkidle", timeout=10000)
            print("✅ Login successful!")
            
            # Navigate to System
            print("📊 Step 3: Navigating to System page...")
            page.click('a:has-text("System")')
            page.wait_for_load_state("networkidle", timeout=10000)
            
            # Switch to Expert mode
            print("🔧 Step 4: Switching to Expert mode...")
            expert_mode = page.locator('label:has-text("Expert")').first
            if expert_mode.is_visible(timeout=3000):
                expert_mode.click()
                page.wait_for_timeout(2000)
                print("✅ Switched to Expert mode")
            else:
                print("⚠️ Expert mode toggle not found")
            
            # Take screenshot of current state
            print("📸 Taking screenshot of System page...")
            Path("artifacts/screenshots").mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            page.screenshot(path=f"artifacts/screenshots/final_system_state_{timestamp}.png", full_page=True)
            
            # Look for Bridges section or tab
            print("🔍 Looking for Bridges section...")
            
            # Check for various possible bridge locations
            bridges_found = False
            bridge_selectors = [
                '[role="tab"]:has-text("Bridges")',
                'button:has-text("Bridges")', 
                '.ant-tabs-tab:has-text("Bridges")',
                'text=Bridges',
                '[data-testid*="bridge"]'
            ]
            
            for selector in bridge_selectors:
                if page.locator(selector).is_visible(timeout=2000):
                    print(f"✅ Found bridges element: {selector}")
                    page.locator(selector).first.click()
                    page.wait_for_timeout(2000)
                    bridges_found = True
                    break
            
            if not bridges_found:
                # Try looking for regions first (bridges might be region-dependent)
                print("🔍 Looking for Regions first...")
                regions_tab = page.locator('text=Regions').first
                if regions_tab.is_visible(timeout=3000):
                    regions_tab.click()
                    page.wait_for_timeout(2000)
                    
                    # Select first region if available
                    region_items = page.locator('.ant-list-item, .region-item, [data-testid*="region"]')
                    if region_items.count() > 0:
                        print("📍 Selecting first region...")
                        region_items.first.click()
                        page.wait_for_timeout(2000)
                        
                        # Now look for bridges
                        for selector in bridge_selectors:
                            if page.locator(selector).is_visible(timeout=2000):
                                print(f"✅ Found bridges after selecting region: {selector}")
                                page.locator(selector).first.click() 
                                page.wait_for_timeout(2000)
                                bridges_found = True
                                break
            
            # Take screenshot of bridges section if found
            if bridges_found:
                print("📸 Taking screenshot of bridges section...")
                page.screenshot(path=f"artifacts/screenshots/final_bridges_section_{timestamp}.png", full_page=True)
                
                # Look for Create Bridge button
                create_selectors = [
                    'button:has-text("Create Bridge")',
                    '[data-testid="system-create-bridge-button"]',
                    'button[aria-label*="Create"]',
                    'button.ant-btn-primary:has([aria-label*="plus"])'
                ]
                
                create_found = False
                for selector in create_selectors:
                    if page.locator(selector).is_visible(timeout=2000):
                        print(f"✅ Found Create Bridge button: {selector}")
                        page.locator(selector).first.click()
                        page.wait_for_timeout(2000)
                        create_found = True
                        break
                
                if create_found:
                    print("📸 Taking screenshot of create bridge modal...")
                    page.screenshot(path=f"artifacts/screenshots/final_create_modal_{timestamp}.png", full_page=True)
                    
                    # Try to fill the form
                    print("📝 Attempting to fill bridge creation form...")
                    
                    # Select team
                    team_dropdown = page.locator('select, .ant-select').first
                    if team_dropdown.is_visible(timeout=2000):
                        if team_dropdown.get_attribute("tagName") == "SELECT":
                            team_dropdown.select_option(label="Private Team")
                        else:
                            team_dropdown.click()
                            page.wait_for_timeout(500)
                            page.locator('.ant-select-item:has-text("Private Team")').first.click()
                        print("✅ Private Team selected")
                    
                    # Enter bridge name
                    name_inputs = page.locator('input[type="text"]').all()
                    if len(name_inputs) > 0:
                        # Use the last input (likely the name field)
                        name_inputs[-1].fill("test_bridge_mcp")
                        print("✅ Bridge name entered: test_bridge_mcp")
                    
                    # Submit form
                    submit_button = page.locator('button:has-text("Create"), button:has-text("OK")').first
                    if submit_button.is_visible(timeout=2000):
                        submit_button.click()
                        page.wait_for_timeout(3000)
                        print("✅ Form submitted")
                        
                        # Check for success
                        success_found = False
                        success_selectors = [
                            'text*="Bridge configuration for network connectivity"',
                            'text*="successfully created"',
                            '.ant-message-success'
                        ]
                        
                        for selector in success_selectors:
                            if page.locator(selector).is_visible(timeout=3000):
                                success_found = True
                                print(f"✅ Success indicator found: {selector}")
                                break
                        
                        if success_found:
                            print("🎉 BRIDGE CREATION SUCCESSFUL!")
                        else:
                            print("⚠️ Bridge creation status unclear")
                        
                        # Final screenshot
                        print("📸 Taking final screenshot...")
                        page.screenshot(path=f"artifacts/screenshots/final_result_{timestamp}.png", full_page=True)
                    else:
                        print("❌ Could not find submit button")
                else:
                    print("❌ Could not find Create Bridge button")
            else:
                print("❌ Could not find Bridges section")
            
            print(f"\n📊 Console Messages Captured: {len(console_messages)}")
            for msg in console_messages[-10:]:  # Show last 10 messages
                print(f"   {msg['type']}: {msg['text']}")
                
        except Exception as e:
            print(f"❌ Test failed: {e}")
            page.screenshot(path=f"artifacts/screenshots/final_error_{timestamp}.png", full_page=True)
            
        finally:
            browser.close()

if __name__ == "__main__":
    run_bridge_test_with_console_capture()