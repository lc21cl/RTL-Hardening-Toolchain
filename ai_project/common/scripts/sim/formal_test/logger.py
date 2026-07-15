#!/usr/bin/env python3
"""
logger.py — 结构化日志系统

提供统一的日志记录接口，支持控制台输出和文件日志。
替代项目中分散的 print 语句。

用法:
    from logger import logger

    logger.info("训练开始")
    logger.warning("模型未加载", module="inference")
    logger.error("文件不存在", file="data.pt", exc_info=True)

    # 替代 print
    logger.print("=" * 60)   # 保留格式化输出到 console
    logger.section("训练结果")  # 带边框的分隔符
"""

import os
import sys
import logging
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime
from logging.handlers import RotatingFileHandler

try:
    from config import config
except ImportError:
    config = None


# ============================================================================
# Log Levels
# ============================================================================

TRACE = 5
VERBOSE = 15

logging.addLevelName(TRACE, 'TRACE')
logging.addLevelName(VERBOSE, 'VERBOSE')


# ============================================================================
# Custom Log Formatter (structured JSON + readable console)
# ============================================================================

class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器。

    支持:
      - 控制台输出: 带颜色/时间戳/模块的可读格式
      - JSON 输出: 结构化格式 (用于文件/ELK)
    """

    COLORS = {
        'TRACE': '\033[37m',      # White
        'DEBUG': '\033[36m',      # Cyan
        'VERBOSE': '\033[35m',    # Magenta
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[41m',   # Red background
        'RESET': '\033[0m',       # Reset
    }

    def __init__(self, fmt_type: str = 'console'):
        """Initialize formatter.

        Args:
            fmt_type: 'console' or 'json'
        """
        super().__init__()
        self.fmt_type = fmt_type

    def format(self, record: logging.LogRecord) -> str:
        if self.fmt_type == 'json':
            return self._format_json(record)
        return self._format_console(record)

    def _format_console(self, record: logging.LogRecord) -> str:
        """Format for console output with colors."""
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        level = record.levelname
        color = self.COLORS.get(level, self.COLORS['RESET'])
        reset = self.COLORS['RESET']

        # Module / component
        module = getattr(record, 'module', record.name) or ''

        # Message with extra fields
        extras = ''
        if hasattr(record, 'extra_fields') and record.extra_fields:
            extras = '  ' + '  '.join(
                f'{k}={v}' for k, v in record.extra_fields.items()
            )

        # Shorten module path
        if module.count('.') > 2:
            parts = module.split('.')
            module = '.'.join(parts[-2:])

        return (
            f'{color}{timestamp:>8s} {level:<8s}{reset} '
            f'[{module}] {record.getMessage()}{extras}'
        )

    def _format_json(self, record: logging.LogRecord) -> str:
        """Format as JSON for file output."""
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'module': getattr(record, 'module', record.name) or '',
            'message': record.getMessage(),
        }

        if hasattr(record, 'extra_fields') and record.extra_fields:
            log_entry.update(record.extra_fields)

        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


# ============================================================================
# Custom Logger
# ============================================================================

class PipelineLogger(logging.Logger):
    """统一的管线日志记录器。

    扩展标准 Logger:
      - .print() — 直接打印到控制台 (不记录到文件)
      - .section() — 带边框的分隔行
      - .trace() — 极详细日志
      - .verbose() — 详细日志
      - .progress() — 进度记录
    """

    def __init__(self, name: str = 'pipeline', level: int = logging.INFO):
        super().__init__(name, level)
        self._extra_fields: Dict[str, Any] = {}

    def _log_with_extra(self, level, msg, args, **kwargs):
        """Log with extra context fields."""
        exc_info = kwargs.pop('exc_info', None)
        extra = kwargs.pop('extra', {})

        if self._extra_fields:
            extra.setdefault('extra_fields', dict(self._extra_fields))

        # Handle individual extra keyword args
        extra_fields = extra.get('extra_fields', {})
        for key, value in kwargs.items():
            extra_fields[key] = str(value)
        if extra_fields:
            extra['extra_fields'] = extra_fields

        super()._log(level, msg, args, exc_info=exc_info, extra=extra)

    def trace(self, msg, *args, **kwargs):
        """TRACE level: extremely detailed logging."""
        if self.isEnabledFor(TRACE):
            self._log_with_extra(TRACE, msg, args, **kwargs)

    def verbose(self, msg, *args, **kwargs):
        """VERBOSE level: detailed but not debug."""
        if self.isEnabledFor(VERBOSE):
            self._log_with_extra(VERBOSE, msg, args, **kwargs)

    def progress(self, current: int, total: int, msg: str = '',
                  bar_length: int = 30):
        """Log progress bar.

        Args:
            current: Current step
            total: Total steps
            msg: Optional message
            bar_length: Progress bar length in characters
        """
        if total <= 0:
            return
        pct = current / total
        filled = int(bar_length * pct)
        bar = '█' * filled + '░' * (bar_length - filled)
        self.info(f'[{bar}] {current}/{total} ({pct*100:.1f}%)  {msg}')

    def print(self, msg: str, **kwargs):
        """Direct print to console (bypasses file logging).

        Use this for formatted output like separator lines.
        """
        # 'print' is not a standard logging level; we use INFO but
        # mark it for console-only output via extra.
        extra = {'extra_fields': {'_console_only': 'true'}}
        super()._log(logging.INFO, msg, (), extra=extra)

    def section(self, title: str, width: int = 62, char: str = '='):
        """Print a section header with border.

        Example:
            ===============================
              Section Title
            ===============================
        """
        self.print(f'\n{char * width}')
        self.print(f'  {title}')
        self.print(f'{char * width}')

    def sub_section(self, title: str):
        """Print a sub-section header."""
        self.print(f'\n{"-" * 48}')
        self.print(f'  {title}')
        self.print(f'{"-" * 48}')

    def metric(self, name: str, value: float, unit: str = ''):
        """Log a metric value.

        Args:
            name: Metric name
            value: Metric value
            unit: Optional unit string
        """
        unit_str = f' {unit}' if unit else ''
        self.info(f'  {name:25s}: {value:.4f}{unit_str}')

    def table(self, headers: list, rows: list, title: str = ''):
        """Log a formatted table.

        Args:
            headers: Column header strings
            rows: List of row tuples
            title: Optional title
        """
        if title:
            self.print(f'\n  {title}:')
            self.print(f'  {"-" * 60}')

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

        # Header
        header_line = '  ' + '  '.join(
            h.ljust(w) for h, w in zip(headers, col_widths)
        )
        self.print(header_line)
        self.print('  ' + '-' * (sum(col_widths) + 2 * (len(headers) - 1)))

        # Rows
        for row in rows:
            self.print(
                '  ' + '  '.join(
                    str(c).ljust(w) for c, w in zip(row, col_widths)
                )
            )


# ============================================================================
# Logger Factory
# ============================================================================

_INITIALIZED_LOGGERS = set()

def setup_logger(name: str = 'pipeline',
                  log_file: Optional[str] = None,
                  log_level: str = 'INFO',
                  console_output: bool = True,
                  json_format: bool = False,
                  force: bool = False) -> PipelineLogger:
    """Create and configure a PipelineLogger instance.

    Args:
        name: Logger name
        log_file: Path to log file (optional)
        log_level: 'TRACE', 'DEBUG', 'INFO', 'WARNING', 'ERROR'
        console_output: Enable console output
        json_format: Use JSON format for file output
        force: Force reconfiguration even if already initialized

    Returns:
        Configured PipelineLogger instance
    """
    if name in _INITIALIZED_LOGGERS and not force:
        return logging.getLogger(name)

    logging.setLoggerClass(PipelineLogger)
    logger = logging.getLogger(name)

    logger.handlers.clear()

    # Parse log level
    level_map = {
        'TRACE': TRACE,
        'DEBUG': logging.DEBUG,
        'VERBOSE': VERBOSE,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }
    numeric_level = level_map.get(log_level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(StructuredFormatter('console'))
        logger.addHandler(console_handler)

    # File handler
    if log_file:
        os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
        file_fmt = 'json' if json_format else 'console'
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding='utf-8',
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(StructuredFormatter(file_fmt))
        logger.addHandler(file_handler)

    _INITIALIZED_LOGGERS.add(name)
    logger.print(f'[Logger] Level={log_level}, File={log_file or "none"}')

    return logger


# ============================================================================
# Create Default Logger
# ============================================================================

# Determine log level from config
_log_level = 'INFO'
_log_file = None

if config is not None:
    _log_level = config.get('logging.level', 'INFO')
    _log_file = config.get('logging.file', None)
    if _log_file:
        scripts_dir = config.get('paths.scripts_dir', '.')
        logs_dir = config.get('paths.logs_dir', 'logs/')
        _log_file = os.path.join(scripts_dir, logs_dir, _log_file)

logger = setup_logger(
    name='pipeline',
    log_file=_log_file,
    log_level=_log_level,
)


# ============================================================================
# Convenience Functions
# ============================================================================

def get_logger(name: str = 'pipeline') -> PipelineLogger:
    """Get a PipelineLogger by name.

    Args:
        name: Logger name

    Returns:
        PipelineLogger instance
    """
    return logging.getLogger(name)


# ============================================================================
# Demo / Test
# ============================================================================

if __name__ == '__main__':
    logger = setup_logger(name='demo', log_level='TRACE',
                           console_output=True)

    logger.section('Logger Demo')
    logger.trace('This is TRACE level')
    logger.debug('This is DEBUG level')
    logger.verbose('This is VERBOSE level')
    logger.info('This is INFO level')
    logger.warning('This is WARNING level', module='test')
    logger.error('This is ERROR level', file='test.pt')

    logger.sub_section('Progress Bar')
    for i in range(10):
        logger.progress(i + 1, 10, msg='Processing')

    logger.sub_section('Metrics')
    logger.metric('F1 Score', 0.8987)
    logger.metric('Precision', 0.8306)
    logger.metric('Recall', 0.9791)

    logger.sub_section('Table')
    logger.table(
        headers=['Model', 'F1', 'Param'],
        rows=[
            ('SAGE3-128', '0.8987', '150K'),
            ('SAGE3-64', '0.8503', '80K'),
        ],
        title='Model Comparison'
    )

    logger.section('Demo Complete')
