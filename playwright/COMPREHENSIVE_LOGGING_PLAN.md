# Comprehensive Logging Implementation Plan for Playwright Tests

## Overview
This document outlines a comprehensive logging strategy for the Playwright test suite in the `/console/playwright/` directory, with a focus on the smart folder tests and their dependencies.

## 1. Core Logging Framework

### 1.1 Create `logging_utils.py`
A dedicated logging utilities module that provides:

```python
# Key features to implement:
- StructuredLogger class extending Python's logging module
- Multiple output handlers (file, console, JSON, HTML)
- Automatic log rotation (size-based and time-based)
- Context-aware logging (test name, session ID, timestamp)
- Log level management (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Performance metrics collection
- Correlation ID tracking across test steps
```

### 1.2 Log File Structure
```
logs/
├── sessions/
│   └── {session_id}/
│       ├── test_execution.log      # Main test flow
│       ├── network_activity.log    # HTTP requests/responses
│       ├── browser_console.log     # Browser console messages
│       ├── performance_metrics.log # Timing and resources
│       ├── error_details.log       # Detailed error traces
│       ├── api_tokens.log          # Token rotation (sanitized)
│       ├── user_actions.log        # UI interactions
│       └── summary.json            # Session summary
├── aggregated/
│   ├── daily/
│   ├── weekly/
│   └── monthly/
└── realtime/
    └── current.log                 # Live streaming log
```

## 2. Enhanced Test Base Class (`test_utils.py`)

### 2.1 Automatic Action Logging
```python
# Log every Playwright action automatically:
- page.click() → "Clicked on element: {selector} at {timestamp}"
- page.fill() → "Filled field: {selector} with {value_length} characters"
- page.goto() → "Navigated to: {url}, load time: {duration}ms"
- page.wait_for_selector() → "Waited for: {selector}, found in {duration}ms"
```

### 2.2 Network Activity Logging
```python
# Capture all network activity:
- Request details (URL, method, headers, body)
- Response details (status, headers, body, timing)
- Failed requests with error details
- API token rotation tracking
- Performance metrics (TTFB, download time)
```

### 2.3 Browser Context Logging
```python
# Browser-specific logging:
- Console messages (errors, warnings, logs)
- JavaScript exceptions
- Resource loading failures
- Memory usage snapshots
- CPU usage tracking
- Page crashes or hangs
```

## 3. Test-Specific Logging

### 3.1 For `00_all.py` (Test Orchestrator)
```python
# Session management logging:
- Test execution order and dependencies
- State transfer between tests
- Session repository name tracking
- Test suite initialization/teardown
- Aggregate results and timing
```

## 4. Structured Log Format

### 4.1 JSON Log Entry Example
```json
{
  "timestamp": "2024-01-09T10:30:45.123Z",
  "session_id": "session_abc123",
  "test_name": "03_createrepo.py",
  "level": "INFO",
  "category": "user_action",
  "action": "click",
  "details": {
    "selector": "[data-testid='resource-modal-ok-button']",
    "element_text": "Create",
    "page_url": "http://localhost:7322/console/resources",
    "screenshot": "screenshots/session_abc123/action_45.png"
  },
  "context": {
    "repository_name": "repo_test123",
    "machine_name": "rediacc11",
    "user": "admin@rediacc.io"
  },
  "performance": {
    "action_duration_ms": 245,
    "memory_usage_mb": 156
  }
}
```

### 4.2 Human-Readable Log Format
```
[2024-01-09 10:30:45.123] [INFO] [03_createrepo.py] [session_abc123]
ACTION: Clicked "Create" button
CONTEXT: Creating repository "repo_test123" on machine "rediacc11"
DURATION: 245ms
---
```

## 6. Configuration Management

### 6.1 Extended `config.json`
```json
{
  "logging": {
    "enabled": true,
    "level": "INFO",
    "handlers": ["file", "console", "json"],
    "file_settings": {
      "directory": "./logs",
      "max_size_mb": 100,
      "rotation_count": 10,
      "compression": true
    },
    "categories": {
      "user_actions": "DEBUG",
      "network": "INFO",
      "browser_console": "WARNING",
      "performance": "INFO"
    },
    "filters": {
      "exclude_urls": ["*/health", "*/metrics"],
      "sanitize_fields": ["password", "token", "credential"]
    },
    "alerts": {
      "error_threshold": 5,
      "performance_threshold_ms": 5000,
      "notification_channels": ["console", "file"]
    }
  }
}
```

## 7. Error Handling & Debugging

### 7.1 Enhanced Error Capture
```python
# On test failure, automatically capture:
- Full page HTML dump
- HAR file of network activity
- Browser console logs
- Screenshot with annotations
- Element tree structure
- JavaScript heap snapshot
- Video recording (last 30 seconds)
```

### 7.2 Debug Mode Features
```python
# When DEBUG=true:
- Log element selector resolution
- Show wait condition evaluations
- Track retry attempts with reasons
- Log CDP events
- Record browser viewport
- Save periodic DOM snapshots
```

## 8. Performance Monitoring

### 8.1 Metrics Collection
```python
# Track and log:
- Page load times (DOMContentLoaded, load, networkidle)
- API response times by endpoint
- Resource loading times
- JavaScript execution time
- Memory usage over time
- CPU usage patterns
- Test execution duration
```

### 8.2 Performance Report
```json
{
  "test": "03_createrepo.py",
  "metrics": {
    "total_duration_ms": 45678,
    "page_loads": [
      {"url": "/console/resources", "duration_ms": 1234}
    ],
    "api_calls": [
      {"endpoint": "/api/CreateQueueItem", "duration_ms": 567}
    ],
    "memory_peak_mb": 256,
    "cpu_average_percent": 45
  }
}
```

## 10. Implementation Priorities

### Phase 1 (Core Logging)
1. Implement `logging_utils.py`
2. Enhance `test_utils.py` with basic logging
3. Add file-based logging to all tests
4. Implement structured log format

### Phase 2 (Advanced Features)
1. Add network activity logging
2. Implement performance metrics
3. Create HTML dashboard
4. Add real-time streaming

### Phase 3 (Integration & Analysis)
1. Add export capabilities
2. Implement alerting system
3. Create analysis tools
4. Add CI/CD integration

## 11. Usage Examples

### 11.1 Basic Test Logging
```python
from logging_utils import StructuredLogger

class MyTest(TestBase):
    def __init__(self):
        super().__init__()
        self.logger = StructuredLogger(__name__)
    
    def test_login(self, page):
        self.logger.info("Starting login test", 
                        context={"user": "test@example.com"})
        # Test implementation
```

### 11.2 Performance Tracking
```python
with self.logger.performance_tracker("repository_creation"):
    create_repository(page, config)
# Automatically logs duration and resource usage
```

### 11.3 Error Context
```python
try:
    element = page.click(selector)
except Exception as e:
    self.logger.error("Failed to click element",
                     error=str(e),
                     selector=selector,
                     page_url=page.url,
                     screenshot=self.capture_screenshot())
```

## 12. Best Practices

1. **Log Levels**: Use appropriate levels (DEBUG for development, INFO for CI/CD)
2. **Sensitive Data**: Always sanitize passwords, tokens, and credentials
3. **Performance**: Use async logging for better test performance
4. **Storage**: Implement log rotation to manage disk space
5. **Searchability**: Use consistent key names and structures
6. **Correlation**: Use session IDs to track related events
7. **Visualization**: Create dashboards for common troubleshooting scenarios

## Conclusion

This comprehensive logging system will provide complete visibility into test execution, making debugging easier and providing valuable insights into application behavior and performance. The phased implementation approach ensures that core functionality is available quickly while allowing for advanced features to be added over time.