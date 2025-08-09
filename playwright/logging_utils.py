"""Comprehensive logging utilities for Playwright tests."""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from contextlib import contextmanager
import threading
from logging.handlers import RotatingFileHandler
import traceback


class StructuredLogger:
    """A structured logger that supports multiple output formats and handlers."""
    
    def __init__(self, name: str, session_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """Initialize the structured logger.
        
        Args:
            name: Logger name (usually module name)
            session_id: Unique session identifier
            config: Logging configuration dictionary
        """
        self.name = name
        self.session_id = session_id or self._generate_session_id()
        self.config = config or self._default_config()
        self.context = {}
        self._lock = threading.Lock()
        
        # Create logger
        self.logger = logging.getLogger(f"{name}_{self.session_id}")
        self.logger.setLevel(self._get_log_level(self.config.get('level', 'INFO')))
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers = []
        
        # Setup log directory
        self.log_dir = self._setup_log_directory()
        
        # Setup handlers based on configuration
        self._setup_handlers()
        
        # Log initialization
        self.info("Logger initialized",
            session_id=self.session_id,
            log_dir=str(self.log_dir),
            handlers=self.config.get('handlers', ['console', 'file']))
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{timestamp}_{os.getpid()}"
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default logging configuration."""
        return {
            "enabled": True,
            "level": "INFO",
            "handlers": ["console", "file"],
            "file_settings": {
                "directory": "./logs",
                "max_size_mb": 50,
                "rotation_count": 5,
                "format": "both"
            },
            "console_settings": {
                "format": "text",
                "colorize": True
            },
            "filters": {
                "sanitize_fields": ["password", "token", "credential", "secret"]
            }
        }
    
    def _get_log_level(self, level_str: str) -> int:
        """Convert string log level to logging constant."""
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        return levels.get(level_str.upper(), logging.INFO)
    
    def _setup_log_directory(self) -> Path:
        """Create and return the log directory for this session."""
        base_dir = Path(self.config['file_settings']['directory'])
        session_dir = base_dir / "sessions" / self.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Create symlink to latest session
        latest_link = base_dir / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(session_dir.relative_to(base_dir))
        
        # Create session info file
        session_info = {
            "session_id": self.session_id,
            "start_time": datetime.now().isoformat(),
            "logger_name": self.name,
            "config": self.config
        }
        with open(session_dir / "session_info.json", 'w') as f:
            json.dump(session_info, f, indent=2)
        
        return session_dir
    
    def _setup_handlers(self):
        """Setup logging handlers based on configuration."""
        handlers = self.config.get('handlers', ['console', 'file'])
        
        if 'console' in handlers:
            self._setup_console_handler()
        
        if 'file' in handlers:
            self._setup_file_handlers()
    
    def _setup_console_handler(self):
        """Setup console handler with appropriate formatter."""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.logger.level)
        
        # Create formatter based on settings
        if self.config['console_settings'].get('colorize', True):
            formatter = ColoredFormatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
    
    def _setup_file_handlers(self):
        """Setup file handlers for both text and JSON formats."""
        file_settings = self.config['file_settings']
        max_bytes = file_settings['max_size_mb'] * 1024 * 1024
        backup_count = file_settings['rotation_count']
        format_type = file_settings.get('format', 'both')
        
        # Text file handler
        if format_type in ['text', 'both']:
            text_handler = RotatingFileHandler(
                self.log_dir / "test_execution.log",
                maxBytes=max_bytes,
                backupCount=backup_count
            )
            text_formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s\n'
                '  Context: %(context)s\n'
                '  Extra: %(extra_data)s\n'
                '---',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            text_handler.setFormatter(text_formatter)
            self.logger.addHandler(text_handler)
        
        # JSON file handler
        if format_type in ['json', 'both']:
            json_handler = RotatingFileHandler(
                self.log_dir / "test_execution.json",
                maxBytes=max_bytes,
                backupCount=backup_count
            )
            json_handler.setFormatter(JsonFormatter(self.session_id))
            self.logger.addHandler(json_handler)
    
    def _sanitize_data(self, data: Any) -> Any:
        """Sanitize sensitive data from logs."""
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(field in key.lower() for field in self.config['filters']['sanitize_fields']):
                    sanitized[key] = "***SANITIZED***"
                else:
                    sanitized[key] = self._sanitize_data(value)
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        elif isinstance(data, str):
            # Check if the string might contain sensitive data
            for field in self.config['filters']['sanitize_fields']:
                if field in data.lower():
                    return "***SANITIZED***"
            return data
        elif isinstance(data, Exception):
            # Convert exceptions to string for JSON serialization
            return str(data)
        else:
            return data
    
    def _prepare_log_data(self, message: str, level: str, **kwargs) -> Dict[str, Any]:
        """Prepare log data with context and sanitization."""
        with self._lock:
            # Combine context with kwargs
            log_data = {
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "logger": self.name,
                "level": level,
                "message": message,
                "context": self.context.copy(),
                **kwargs
            }
            
            # Sanitize the data
            return self._sanitize_data(log_data)
    
    def set_context(self, **kwargs):
        """Set context that will be included in all subsequent logs."""
        with self._lock:
            self.context.update(kwargs)
    
    def clear_context(self):
        """Clear the logging context."""
        with self._lock:
            self.context = {}
    
    @contextmanager
    def context_manager(self, **kwargs):
        """Context manager for temporary context."""
        old_context = self.context.copy()
        self.set_context(**kwargs)
        try:
            yield
        finally:
            with self._lock:
                self.context = old_context
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        log_data = self._prepare_log_data(message, "DEBUG", **kwargs)
        self.logger.debug(message, extra={
            'context': json.dumps(log_data.get('context', {})),
            'extra_data': json.dumps({k: v for k, v in log_data.items() 
                                     if k not in ['message', 'context', 'timestamp', 'session_id', 'logger', 'level']})
        })
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        log_data = self._prepare_log_data(message, "INFO", **kwargs)
        self.logger.info(message, extra={
            'context': json.dumps(log_data.get('context', {})),
            'extra_data': json.dumps({k: v for k, v in log_data.items() 
                                     if k not in ['message', 'context', 'timestamp', 'session_id', 'logger', 'level']})
        })
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        log_data = self._prepare_log_data(message, "WARNING", **kwargs)
        self.logger.warning(message, extra={
            'context': json.dumps(log_data.get('context', {})),
            'extra_data': json.dumps({k: v for k, v in log_data.items() 
                                     if k not in ['message', 'context', 'timestamp', 'session_id', 'logger', 'level']})
        })
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        # Include traceback if available
        if 'error' in kwargs and isinstance(kwargs['error'], Exception):
            kwargs['traceback'] = traceback.format_exc()
            # Convert exception to string for JSON serialization
            kwargs['error'] = str(kwargs['error'])
        
        log_data = self._prepare_log_data(message, "ERROR", **kwargs)
        self.logger.error(message, extra={
            'context': json.dumps(log_data.get('context', {})),
            'extra_data': json.dumps({k: v for k, v in log_data.items() 
                                     if k not in ['message', 'context', 'timestamp', 'session_id', 'logger', 'level']})
        })
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        log_data = self._prepare_log_data(message, "CRITICAL", **kwargs)
        self.logger.critical(message, extra={
            'context': json.dumps(log_data.get('context', {})),
            'extra_data': json.dumps({k: v for k, v in log_data.items() 
                                     if k not in ['message', 'context', 'timestamp', 'session_id', 'logger', 'level']})
        })
    
    @contextmanager
    def performance_tracker(self, operation: str, **kwargs):
        """Track performance of an operation."""
        start_time = time.time()
        start_memory = self._get_memory_usage()
        
        self.info(f"Starting operation: {operation}", operation=operation, **kwargs)
        
        try:
            yield
        finally:
            duration = (time.time() - start_time) * 1000  # Convert to milliseconds
            end_memory = self._get_memory_usage()
            memory_delta = end_memory - start_memory
            
            self.info(f"Completed operation: {operation}",
                     operation=operation,
                     duration_ms=round(duration, 2),
                     memory_start_mb=round(start_memory, 2),
                     memory_end_mb=round(end_memory, 2),
                     memory_delta_mb=round(memory_delta, 2),
                     **kwargs)
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            # psutil not available, return 0
            return 0.0
    
    def log_test_start(self, test_name: str, **kwargs):
        """Log the start of a test."""
        self.info(f"Test started: {test_name}",
                 test_name=test_name,
                 category="test_lifecycle",
                 **kwargs)
    
    def log_test_step(self, step_name: str, description: str = "", **kwargs):
        """Log a test step."""
        self.info(f"Test step: {step_name}",
                 step_name=step_name,
                 description=description,
                 category="test_step",
                 **kwargs)
    
    def log_test_end(self, test_name: str, success: bool, duration_ms: float = 0, **kwargs):
        """Log the end of a test."""
        level = "INFO" if success else "ERROR"
        message = f"Test {'passed' if success else 'failed'}: {test_name}"
        
        log_method = self.info if success else self.error
        log_method(message,
                  test_name=test_name,
                  success=success,
                  duration_ms=duration_ms,
                  category="test_lifecycle",
                  **kwargs)


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "session_id": self.session_id,
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add context if available
        if hasattr(record, 'context'):
            try:
                log_data['context'] = json.loads(record.context)
            except:
                log_data['context'] = str(record.context)
        
        # Add extra data if available
        if hasattr(record, 'extra_data'):
            try:
                extra = json.loads(record.extra_data)
                log_data.update(extra)
            except:
                log_data['extra_data'] = str(record.extra_data)
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": [line.strip() for line in traceback.format_exception(*record.exc_info)]
            }
        
        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output."""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        
        formatted = super().format(record)
        
        # Add context and extra data if available
        additional_info = []
        
        if hasattr(record, 'context') and record.context != '{}':
            additional_info.append(f"  Context: {record.context}")
        
        if hasattr(record, 'extra_data') and record.extra_data != '{}':
            additional_info.append(f"  Extra: {record.extra_data}")
        
        if additional_info:
            formatted += '\n' + '\n'.join(additional_info)
        
        return formatted


# Utility functions for common logging patterns

def log_playwright_action(logger: StructuredLogger, action: str, selector: str = "", 
                         element_text: str = "", duration_ms: float = 0, **kwargs):
    """Log a Playwright action with standard format."""
    logger.info(f"Playwright action: {action}",
               category="playwright_action",
               action=action,
               selector=selector,
               element_text=element_text,
               duration_ms=duration_ms,
               **kwargs)


def log_api_call(logger: StructuredLogger, method: str, url: str, 
                 status_code: int = 0, duration_ms: float = 0, **kwargs):
    """Log an API call with standard format."""
    level = "INFO" if 200 <= status_code < 400 else "ERROR"
    log_method = logger.info if level == "INFO" else logger.error
    
    log_method(f"API call: {method} {url}",
              category="api_call",
              method=method,
              url=url,
              status_code=status_code,
              duration_ms=duration_ms,
              **kwargs)


def log_browser_console(logger: StructuredLogger, message_type: str, 
                       message_text: str, source: str = "", **kwargs):
    """Log browser console messages."""
    level_map = {
        'error': 'ERROR',
        'warning': 'WARNING',
        'log': 'INFO',
        'info': 'INFO',
        'debug': 'DEBUG'
    }
    
    level = level_map.get(message_type.lower(), 'INFO')
    log_method = getattr(logger, level.lower())
    
    log_method(f"Browser console: {message_text}",
              category="browser_console",
              console_type=message_type,
              source=source,
              **kwargs)