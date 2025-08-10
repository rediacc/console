"""
Comprehensive Debug Dump Utility for Playwright Tests
This module provides detailed debugging information capture for test analysis
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from playwright.sync_api import Page
import traceback


class DebugDumper:
    """Comprehensive debug information dumper for Playwright tests"""
    
    def __init__(self, output_dir: str = "debug_dumps"):
        """Initialize the debug dumper with output directory"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
    def create_dump(self, page: Page, context: str = "unknown", extra_info: Dict = None) -> str:
        """
        Create a comprehensive dump of the current page state
        
        Args:
            page: Playwright page object
            context: Context description (where/why dump was created)
            extra_info: Additional information to include in dump
            
        Returns:
            Path to the dump file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dump_name = f"dump_{context}_{timestamp}"
        dump_file = self.output_dir / f"{dump_name}.json"
        
        dump_data = {
            "timestamp": timestamp,
            "context": context,
            "extra_info": extra_info or {},
            "page_info": self._get_page_info(page),
            "dom": self._get_dom_info(page),
            "dialogs": self._get_dialog_info(page),
            "console_messages": self._get_console_messages(page),
            "network": self._get_network_info(page),
            "elements": self._get_element_analysis(page),
            "javascript_state": self._get_javascript_state(page),
            "performance": self._get_performance_metrics(page),
            "accessibility": self._get_accessibility_tree(page),
            "screenshots": self._capture_screenshots(page, dump_name)
        }
        
        # Write the dump to file
        with open(dump_file, 'w', encoding='utf-8') as f:
            json.dump(dump_data, f, indent=2, default=str)
        
        # Also create a human-readable summary
        self._create_summary(dump_data, dump_name)
        
        print(f"[DEBUG DUMP] Created: {dump_file}")
        return str(dump_file)
    
    def _get_page_info(self, page: Page) -> Dict:
        """Get basic page information"""
        try:
            return {
                "url": page.url,
                "title": page.title(),
                "viewport": page.viewport_size,
                "is_closed": page.is_closed()
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_dom_info(self, page: Page) -> Dict:
        """Get DOM structure information"""
        try:
            dom_info = {}
            
            # Get full HTML
            dom_info["html_length"] = len(page.content())
            
            # Get body HTML (more manageable size)
            dom_info["body_html"] = page.locator("body").inner_html()[:50000]  # Limit size
            
            # Count various elements
            dom_info["element_counts"] = {
                "total_elements": page.locator("*").count(),
                "buttons": page.locator("button").count(),
                "inputs": page.locator("input").count(),
                "divs": page.locator("div").count(),
                "modals": page.locator("[role='dialog']").count(),
                "modal_wrappers": page.locator(".ant-modal-wrap").count(),
                "alerts": page.locator(".ant-alert").count()
            }
            
            # Get document ready state
            dom_info["ready_state"] = page.evaluate("document.readyState")
            
            return dom_info
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}
    
    def _get_dialog_info(self, page: Page) -> Dict:
        """Get detailed information about all dialog/modal elements"""
        try:
            dialog_info = {
                "all_dialogs": [],
                "visible_dialogs": [],
                "modal_wrappers": [],
                "queue_dialogs": []
            }
            
            # Find all elements with role="dialog"
            dialogs = page.locator("[role='dialog']").all()
            for i, dialog in enumerate(dialogs):
                try:
                    dialog_data = {
                        "index": i,
                        "visible": dialog.is_visible(),
                        "text_content": dialog.text_content()[:500] if dialog.text_content() else None,
                        "inner_html": dialog.inner_html()[:1000],
                        "attributes": self._get_element_attributes(page, dialog),
                        "bounding_box": dialog.bounding_box(),
                        "has_queue_text": "Queue" in (dialog.text_content() or "")
                    }
                    dialog_info["all_dialogs"].append(dialog_data)
                    
                    if dialog_data["visible"]:
                        dialog_info["visible_dialogs"].append(dialog_data)
                    
                    if dialog_data["has_queue_text"]:
                        dialog_info["queue_dialogs"].append(dialog_data)
                except Exception as e:
                    dialog_info["all_dialogs"].append({"index": i, "error": str(e)})
            
            # Find all modal wrappers
            modal_wrappers = page.locator(".ant-modal-wrap").all()
            for i, wrapper in enumerate(modal_wrappers):
                try:
                    wrapper_data = {
                        "index": i,
                        "visible": wrapper.is_visible(),
                        "classes": wrapper.get_attribute("class"),
                        "has_hidden_class": "ant-modal-wrap-hidden" in (wrapper.get_attribute("class") or ""),
                        "contains_dialog": wrapper.locator("[role='dialog']").count() > 0,
                        "text_preview": wrapper.text_content()[:200] if wrapper.text_content() else None
                    }
                    dialog_info["modal_wrappers"].append(wrapper_data)
                except Exception as e:
                    dialog_info["modal_wrappers"].append({"index": i, "error": str(e)})
            
            # Check for Queue Item Trace specifically
            dialog_info["queue_trace_search"] = {
                "by_text": page.locator('text="Queue Item Trace"').count(),
                "by_role_and_text": page.locator('[role="dialog"]:has-text("Queue Item Trace")').count(),
                "visible_by_text": page.locator('text="Queue Item Trace"').all()[0].is_visible() if page.locator('text="Queue Item Trace"').count() > 0 else False,
                "in_modal_wrap": page.locator('.ant-modal-wrap:has-text("Queue Item Trace")').count(),
                "in_visible_modal": page.locator('.ant-modal-wrap:not(.ant-modal-wrap-hidden):has-text("Queue Item Trace")').count()
            }
            
            return dialog_info
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}
    
    def _get_element_attributes(self, page: Page, element) -> Dict:
        """Get all attributes of an element"""
        try:
            # Use JavaScript to get all attributes
            return page.evaluate("""
                (element) => {
                    const attrs = {};
                    for (const attr of element.attributes) {
                        attrs[attr.name] = attr.value;
                    }
                    return attrs;
                }
            """, element)
        except:
            return {}
    
    def _get_console_messages(self, page: Page) -> List[Dict]:
        """Get console messages (if handler was set up)"""
        try:
            # This would need to be set up beforehand with page.on("console")
            # For now, we'll try to get what we can from JavaScript
            logs = page.evaluate("""
                () => {
                    // Try to capture any stored console logs if available
                    if (window.__consoleLogs) {
                        return window.__consoleLogs;
                    }
                    return [];
                }
            """)
            return logs if logs else []
        except Exception as e:
            return [{"error": str(e)}]
    
    def _get_network_info(self, page: Page) -> Dict:
        """Get network request information"""
        try:
            # Get recent API calls from browser
            recent_calls = page.evaluate("""
                () => {
                    if (window.performance && window.performance.getEntriesByType) {
                        const entries = window.performance.getEntriesByType('resource');
                        return entries.slice(-20).map(e => ({
                            name: e.name,
                            duration: e.duration,
                            type: e.initiatorType,
                            size: e.transferSize
                        }));
                    }
                    return [];
                }
            """)
            return {"recent_requests": recent_calls}
        except Exception as e:
            return {"error": str(e)}
    
    def _get_element_analysis(self, page: Page) -> Dict:
        """Analyze specific elements we care about"""
        try:
            analysis = {
                "queue_related_elements": {},
                "buttons": {},
                "dropdowns": {}
            }
            
            # Queue-related elements
            queue_selectors = [
                "button:has-text('Close')",
                "[data-testid='queue-trace-close-button']",
                ".ant-alert-success",
                "text=/Task Completed Successfully/",
                "text=/Duration/",
                ".ant-steps",
                ".ant-dropdown-menu-item:has-text('down')"
            ]
            
            for selector in queue_selectors:
                try:
                    elements = page.locator(selector).all()
                    analysis["queue_related_elements"][selector] = {
                        "count": len(elements),
                        "visible_count": sum(1 for e in elements if e.is_visible()),
                        "details": [
                            {
                                "visible": e.is_visible(),
                                "text": e.text_content()[:100] if e.text_content() else None,
                                "bbox": e.bounding_box()
                            } for e in elements[:3]  # Limit to first 3
                        ]
                    }
                except Exception as e:
                    analysis["queue_related_elements"][selector] = {"error": str(e)}
            
            # All visible buttons
            visible_buttons = page.locator("button:visible").all()
            analysis["buttons"]["visible_count"] = len(visible_buttons)
            analysis["buttons"]["visible_texts"] = [
                b.text_content()[:50] for b in visible_buttons[:10]
            ]
            
            # Check for dropdowns
            analysis["dropdowns"]["ant_dropdown_visible"] = page.locator(".ant-dropdown:not(.ant-dropdown-hidden)").count()
            analysis["dropdowns"]["menu_items"] = page.locator(".ant-dropdown-menu-item").count()
            
            return analysis
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}
    
    def _get_javascript_state(self, page: Page) -> Dict:
        """Execute JavaScript to get page state"""
        try:
            state = page.evaluate("""
                () => {
                    return {
                        // Check for React/Redux state if available
                        hasReact: typeof React !== 'undefined',
                        hasRedux: typeof window.__REDUX_DEVTOOLS_EXTENSION__ !== 'undefined',
                        
                        // Get Ant Design modal state
                        antModals: Array.from(document.querySelectorAll('.ant-modal-wrap')).map(m => ({
                            classes: m.className,
                            style: m.getAttribute('style'),
                            visible: !m.classList.contains('ant-modal-wrap-hidden'),
                            hasDialog: m.querySelector('[role="dialog"]') !== null,
                            dialogTitle: m.querySelector('.ant-modal-title')?.textContent
                        })),
                        
                        // Check for any global state
                        windowKeys: Object.keys(window).filter(k => k.startsWith('__')),
                        
                        // Document state
                        documentState: {
                            readyState: document.readyState,
                            hidden: document.hidden,
                            visibilityState: document.visibilityState,
                            activeElement: document.activeElement?.tagName
                        },
                        
                        // Check for animations
                        animations: document.getAnimations ? document.getAnimations().length : 0
                    };
                }
            """)
            return state
        except Exception as e:
            return {"error": str(e), "traceback": traceback.format_exc()}
    
    def _get_performance_metrics(self, page: Page) -> Dict:
        """Get performance metrics"""
        try:
            metrics = page.evaluate("""
                () => {
                    const perf = window.performance;
                    return {
                        timing: perf.timing ? {
                            domContentLoaded: perf.timing.domContentLoadedEventEnd - perf.timing.navigationStart,
                            loadComplete: perf.timing.loadEventEnd - perf.timing.navigationStart
                        } : null,
                        memory: perf.memory ? {
                            usedJSHeapSize: perf.memory.usedJSHeapSize,
                            totalJSHeapSize: perf.memory.totalJSHeapSize
                        } : null,
                        navigation: {
                            type: perf.navigation?.type,
                            redirectCount: perf.navigation?.redirectCount
                        }
                    };
                }
            """)
            return metrics
        except Exception as e:
            return {"error": str(e)}
    
    def _get_accessibility_tree(self, page: Page) -> Dict:
        """Get accessibility tree for dialogs"""
        try:
            # Get accessibility tree for dialog elements
            dialogs = page.locator("[role='dialog']").all()
            trees = []
            for i, dialog in enumerate(dialogs[:3]):  # Limit to first 3
                try:
                    tree = page.accessibility.snapshot(root=dialog)
                    trees.append({"index": i, "tree": tree})
                except:
                    trees.append({"index": i, "tree": None})
            return {"dialog_trees": trees}
        except Exception as e:
            return {"error": str(e)}
    
    def _capture_screenshots(self, page: Page, dump_name: str) -> Dict:
        """Capture various screenshots"""
        screenshots = {}
        try:
            # Full page screenshot
            full_path = self.output_dir / f"{dump_name}_full.png"
            page.screenshot(path=str(full_path), full_page=True)
            screenshots["full_page"] = str(full_path)
            
            # Viewport screenshot
            viewport_path = self.output_dir / f"{dump_name}_viewport.png"
            page.screenshot(path=str(viewport_path))
            screenshots["viewport"] = str(viewport_path)
            
            # Try to capture visible dialogs
            visible_dialogs = page.locator("[role='dialog']:visible").all()
            for i, dialog in enumerate(visible_dialogs[:3]):
                try:
                    dialog_path = self.output_dir / f"{dump_name}_dialog_{i}.png"
                    dialog.screenshot(path=str(dialog_path))
                    screenshots[f"dialog_{i}"] = str(dialog_path)
                except:
                    pass
            
        except Exception as e:
            screenshots["error"] = str(e)
        
        return screenshots
    
    def _create_summary(self, dump_data: Dict, dump_name: str) -> None:
        """Create a human-readable summary of the dump"""
        summary_file = self.output_dir / f"{dump_name}_SUMMARY.txt"
        
        with open(summary_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write(f"DEBUG DUMP SUMMARY - {dump_data['timestamp']}\n")
            f.write(f"Context: {dump_data['context']}\n")
            f.write("=" * 80 + "\n\n")
            
            # Page info
            f.write("PAGE INFO:\n")
            f.write(f"  URL: {dump_data['page_info'].get('url', 'unknown')}\n")
            f.write(f"  Title: {dump_data['page_info'].get('title', 'unknown')}\n\n")
            
            # Dialog summary
            f.write("DIALOG ANALYSIS:\n")
            if 'dialogs' in dump_data and 'all_dialogs' in dump_data['dialogs']:
                f.write(f"  Total dialogs found: {len(dump_data['dialogs']['all_dialogs'])}\n")
                f.write(f"  Visible dialogs: {len(dump_data['dialogs'].get('visible_dialogs', []))}\n")
                f.write(f"  Queue-related dialogs: {len(dump_data['dialogs'].get('queue_dialogs', []))}\n")
                f.write(f"  Modal wrappers: {len(dump_data['dialogs'].get('modal_wrappers', []))}\n")
                
                f.write("\n  Queue Trace Search Results:\n")
                if 'queue_trace_search' in dump_data['dialogs']:
                    for key, value in dump_data['dialogs']['queue_trace_search'].items():
                        f.write(f"    {key}: {value}\n")
                
                f.write("\n  Dialog Details:\n")
                for dialog in dump_data['dialogs']['all_dialogs'][:5]:
                    f.write(f"    Dialog {dialog.get('index', '?')}:\n")
                    f.write(f"      Visible: {dialog.get('visible', '?')}\n")
                    f.write(f"      Has Queue text: {dialog.get('has_queue_text', '?')}\n")
                    if dialog.get('text_content'):
                        f.write(f"      Text preview: {dialog['text_content'][:100]}...\n")
                    f.write("\n")
            
            # Element counts
            if 'dom' in dump_data and 'element_counts' in dump_data['dom']:
                f.write("\nELEMENT COUNTS:\n")
                for elem_type, count in dump_data['dom']['element_counts'].items():
                    f.write(f"  {elem_type}: {count}\n")
            
            # JavaScript state
            if 'javascript_state' in dump_data and 'antModals' in dump_data['javascript_state']:
                f.write("\nANT MODALS STATE:\n")
                for i, modal in enumerate(dump_data['javascript_state']['antModals']):
                    f.write(f"  Modal {i}:\n")
                    f.write(f"    Visible: {modal.get('visible', '?')}\n")
                    f.write(f"    Has Dialog: {modal.get('hasDialog', '?')}\n")
                    f.write(f"    Title: {modal.get('dialogTitle', 'none')}\n")
            
            # Queue-related elements
            if 'elements' in dump_data and 'queue_related_elements' in dump_data['elements']:
                f.write("\nQUEUE-RELATED ELEMENTS:\n")
                for selector, info in dump_data['elements']['queue_related_elements'].items():
                    if not isinstance(info, dict) or 'error' in info:
                        continue
                    f.write(f"  {selector}:\n")
                    f.write(f"    Count: {info.get('count', 0)}\n")
                    f.write(f"    Visible: {info.get('visible_count', 0)}\n")
            
            # Screenshots
            if 'screenshots' in dump_data:
                f.write("\nSCREENSHOTS CAPTURED:\n")
                for name, path in dump_data['screenshots'].items():
                    if name != 'error':
                        f.write(f"  {name}: {path}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"Full dump saved to: {self.output_dir / f'{dump_name}.json'}\n")
            f.write("=" * 80 + "\n")


def quick_dump(page: Page, context: str = "debug", extra_info: Dict = None) -> str:
    """Quick function to create a dump without instantiating the class"""
    dumper = DebugDumper()
    return dumper.create_dump(page, context, extra_info)