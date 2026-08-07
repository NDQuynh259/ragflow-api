"""Terminal logging configuration shared by the application."""

import logging


class ColorFormatter(logging.Formatter):
    """Format log levels with ANSI colors for terminal output."""

    COLORS = {
        logging.DEBUG: "\033[36m",      # Cyan
        logging.INFO: "\033[32m",       # Green
        logging.WARNING: "\033[33m",    # Yellow
        logging.ERROR: "\033[31m",      # Red
        logging.CRITICAL: "\033[1;31m", # Bright red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        color = self.COLORS.get(record.levelno, "")
        record.levelname = f"{color}{original_levelname}{self.RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


def configure_logging() -> None:
    """Configure colored application logs in the Uvicorn-style terminal format."""
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter("%(levelname)s:     %(message)s | %(asctime)s"))

    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[console_handler],
        force=True,
    )
