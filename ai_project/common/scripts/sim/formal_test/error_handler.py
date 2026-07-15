#!/usr/bin/env python3
"""
error_handler.py — 统一异常捕获与错误处理框架

提供:
  - PipelineError 及其子类 (ConfigError, ModelError, DataError 等)
  - safe_run 装饰器 (异常捕获 + 日志 + 可配置重试)
  - ErrorCollector (批量处理时收集多个错误)

用法:
    from error_handler import safe_run, ErrorCollector, PipelineError

    @safe_run(logger=logger, max_retries=2)
    def process_file(path):
        ...

    collector = ErrorCollector()
    for f in files:
        with collector.collect():
            process(f)
    collector.summary()
"""

import functools
import logging
import time
import traceback
import sys
from typing import Optional, Callable, Any, Dict, List, Type


# ============================================================================
# Exception Hierarchy
# ============================================================================

class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    def __init__(self, message: str, code: Optional[str] = None,
                 details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.code = code or 'UNKNOWN'
        self.details = details or {}

    def __str__(self):
        parts = [f"[{self.code}] {self.message}"]
        if self.details:
            parts.append(f"  details: {self.details}")
        return '\n'.join(parts)


class ConfigError(PipelineError):
    """Configuration-related errors."""
    def __init__(self, message: str, key: Optional[str] = None,
                 details: Optional[Dict] = None):
        d = details or {}
        if key:
            d['key'] = key
        super().__init__(message, code='CONFIG_ERROR', details=d)


class ModelError(PipelineError):
    """Model loading/inference errors."""
    def __init__(self, message: str, model_path: Optional[str] = None,
                 details: Optional[Dict] = None):
        d = details or {}
        if model_path:
            d['model_path'] = model_path
        super().__init__(message, code='MODEL_ERROR', details=d)


class DataError(PipelineError):
    """Data conversion/processing errors."""
    def __init__(self, message: str, file_path: Optional[str] = None,
                 details: Optional[Dict] = None):
        d = details or {}
        if file_path:
            d['file_path'] = file_path
        super().__init__(message, code='DATA_ERROR', details=d)


class SynthesisError(PipelineError):
    """RTL synthesis errors (yosys)."""
    def __init__(self, message: str, rtl_path: Optional[str] = None,
                 exit_code: Optional[int] = None,
                 details: Optional[Dict] = None):
        d = details or {}
        if rtl_path:
            d['rtl_path'] = rtl_path
        if exit_code is not None:
            d['exit_code'] = exit_code
        super().__init__(message, code='SYNTHESIS_ERROR', details=d)


class ConversionError(PipelineError):
    """File format conversion errors."""
    def __init__(self, message: str, file_path: Optional[str] = None,
                 details: Optional[Dict] = None):
        d = details or {}
        if file_path:
            d['file_path'] = file_path
        super().__init__(message, code='CONVERSION_ERROR', details=d)


class ValidationError(PipelineError):
    """Data/model validation errors."""
    def __init__(self, message: str, field: Optional[str] = None,
                 expected: Any = None, actual: Any = None,
                 details: Optional[Dict] = None):
        d = details or {}
        if field:
            d['field'] = field
        if expected is not None:
            d['expected'] = str(expected)
        if actual is not None:
            d['actual'] = str(actual)
        super().__init__(message, code='VALIDATION_ERROR', details=d)


# ============================================================================
# Error-to-exception mapping
# ============================================================================

# Map common exception types to our pipeline errors
ERROR_MAP: Dict[Type[Exception], Type[PipelineError]] = {
    FileNotFoundError: DataError,
    PermissionError: DataError,
    ValueError: ValidationError,
    TypeError: ValidationError,
    RuntimeError: PipelineError,
    ImportError: ConfigError,
    ModuleNotFoundError: ConfigError,
}


def _map_exception(exc: Exception, **context) -> PipelineError:
    """Map a generic exception to a PipelineError subclass."""
    for src_type, dst_type in ERROR_MAP.items():
        if isinstance(exc, src_type):
            return dst_type(str(exc), **context)
    return PipelineError(str(exc), details=context)


# ============================================================================
# safe_run decorator
# ============================================================================

def safe_run(
    logger: Optional[logging.Logger] = None,
    on_error: Optional[Callable] = None,
    reraise: bool = True,
    max_retries: int = 0,
    retry_delay: float = 1.0,
    retry_backoff: float = 2.0,
    error_type: Type[PipelineError] = None,
    **context,
):
    """Decorator for safe function execution with retry support.

    Args:
        logger: Logger instance for error logging
        on_error: Callback function on error (receives exception)
        reraise: If True, re-raise PipelineError; if False, return None
        max_retries: Maximum retry attempts (0 = no retry)
        retry_delay: Initial delay between retries (seconds)
        retry_backoff: Multiplicative backoff factor
        error_type: Override error type for all exceptions
        **context: Additional context passed to PipelineError details

    Usage:
        @safe_run(logger=logger, max_retries=2, reraise=False)
        def risky_operation(path):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            delay = retry_delay
            log = logger or logging.getLogger(func.__module__)

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except PipelineError:
                    # Already a PipelineError, just re-raise
                    if reraise:
                        raise
                    return None
                except Exception as exc:
                    last_exc = exc
                    mapped = _map_exception(exc, **context)
                    if error_type:
                        mapped = error_type(str(exc), **context)

                    log.error(
                        "%s.%s failed (attempt %d/%d): %s [%s]",
                        func.__module__, func.__qualname__,
                        attempt + 1, max_retries + 1,
                        mapped.message, mapped.code,
                    )

                    if on_error:
                        try:
                            on_error(mapped)
                        except Exception:
                            pass

                    if attempt < max_retries:
                        log.info("  Retrying in %.1fs...", delay)
                        time.sleep(delay)
                        delay *= retry_backoff

            # All retries exhausted
            if reraise:
                if isinstance(last_exc, PipelineError):
                    raise last_exc
                mapped = _map_exception(last_exc, **context)
                if error_type:
                    mapped = error_type(str(last_exc), **context)
                raise mapped

            return None
        return wrapper
    return decorator


# ============================================================================
# ErrorCollector
# ============================================================================

class ErrorCollector:
    """Collect errors during batch processing without stopping.

    Usage:
        collector = ErrorCollector()
        for file in files:
            with collector.collect():
                process(file)
        collector.summary()  # prints summary
        if collector.has_errors:
            pass  # handle failed items
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.errors: List[Dict] = []
        self.success_count = 0
        self.fail_count = 0
        self._log = logger or logging.getLogger(__name__)

    @property
    def has_errors(self) -> bool:
        return self.fail_count > 0

    @property
    def total(self) -> int:
        return self.success_count + self.fail_count

    def collect(self, context: Optional[Dict] = None):
        """Context manager that catches exceptions and records them."""
        return _ErrorCollectorCtx(self, context or {})

    def add_error(self, exc: Exception, context: Optional[Dict] = None):
        """Manually record an error."""
        ctx = context or {}
        if isinstance(exc, PipelineError):
            entry = {
                'message': exc.message,
                'code': exc.code,
                'details': {**exc.details, **ctx},
            }
        else:
            mapped = _map_exception(exc, **ctx)
            entry = {
                'message': mapped.message,
                'code': mapped.code,
                'details': {**mapped.details, **ctx},
            }
        self.errors.append(entry)
        self.fail_count += 1
        self._log.error("  [%s] %s", entry['code'], entry['message'])

    def summary(self, title: str = "Error Summary") -> Dict:
        """Print and return error summary statistics."""
        print(f"\n{'=' * 62}")
        print(f"  {title}")
        print(f"{'=' * 62}")
        print(f"  Total:    {self.total}")
        print(f"  Success:  {self.success_count}")
        print(f"  Failed:   {self.fail_count}")

        if self.errors:
            # Group by error code
            from collections import Counter
            code_counts = Counter(e['code'] for e in self.errors)
            print(f"\n  Errors by type:")
            for code, count in code_counts.most_common():
                print(f"    {code:20s} {count:4d}")

            # Show last 5 errors
            print(f"\n  Last {min(5, len(self.errors))} errors:")
            for e in self.errors[-5:]:
                print(f"    [{e['code']}] {e['message'][:80]}")

        print(f"{'=' * 62}")

        return {
            'total': self.total,
            'success': self.success_count,
            'fail': self.fail_count,
            'errors': self.errors,
        }


class _ErrorCollectorCtx:
    """Context manager used internally by ErrorCollector.collect()."""
    def __init__(self, collector: ErrorCollector, context: Dict):
        self.collector = collector
        self.context = context

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is None:
            self.collector.success_count += 1
            return True
        self.collector.add_error(exc_val, self.context)
        return True  # suppress exception
