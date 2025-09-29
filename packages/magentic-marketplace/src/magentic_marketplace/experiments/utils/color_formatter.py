"""Colored logging formatter for experiment scripts."""

import logging
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Colored formatter for logging."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord):
        """Format a log record."""
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        log_color = f"{color}{record.levelname}{self.RESET}"
        name_color = f"\033[34m{record.name}{self.RESET}"  # Blue
        time_color = f"\033[90m({timestamp}){self.RESET}"  # Gray
        return f"{log_color} [{name_color}] {time_color} {record.getMessage()}"


def setup_logging():
    """Set up colorful logging configuration and suppress noisy loggers."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s [%(name)s] (%(asctime)s) %(message)s",
        datefmt="%H:%M:%S",
        handlers=[],
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    logging.getLogger("azure").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
