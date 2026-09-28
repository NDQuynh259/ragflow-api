"""Standardized logging configuration with colored console output."""

from __future__ import annotations

import logging
import os
import sys


class ColoredFormatter(logging.Formatter):
    """Console formatter with ANSI color codes for enhanced readability."""

    RESET = "\033[0m"
    DIM = "\033[90m"
    BOLD = "\033[1m"

    LEVEL_COLORS = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",  # Red
        logging.CRITICAL: "\033[1;31m",  # Bold Red
    }
    NAME_COLOR = "\033[35m"  # Magenta

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = "%Y-%m-%d %H:%M:%S",
        use_colors: bool = True,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        if not self.use_colors:
            return super().format(record)

        color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        asctime = self.formatTime(record, self.datefmt)

        time_part = f"{self.DIM}{asctime}{self.RESET}"
        level_part = f"{color}[{record.levelname}]{self.RESET}"
        name_part = f"{self.NAME_COLOR}{record.name}{self.RESET}"
        message = record.getMessage()

        if record.levelno >= logging.ERROR:
            message_part = f"{color}{message}{self.RESET}"
        else:
            message_part = message

        result = f"{time_part} {level_part} {name_part}: {message_part}"

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            result += f"\n{record.exc_text}"
        if record.stack_info:
            result += f"\n{self.formatStack(record.stack_info)}"

        return result


def setup_logging(level: int = logging.INFO, colored: bool = True) -> None:
    """Configure root logger with unified formatting and ANSI colors."""
    if colored and os.name == "nt":
        # Enable ANSI escape sequences support on Windows console
        os.system("")

    formatter = ColoredFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        use_colors=colored,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Silence overly verbose third-party loggers
    for noisy in ("pika", "httpcore", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Unify uvicorn loggers with root handler
    for u_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        u_logger = logging.getLogger(u_name)
        u_logger.handlers = [handler]
        u_logger.propagate = False
