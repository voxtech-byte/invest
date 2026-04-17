"""
Quant Alpha V11 Pro — Structured Logging Framework

Centralized logging replacing all ad-hoc print() statements.
Features:
- Dual output: Console (colorized) + Rotating file handler
- Module-aware named loggers
- Structured format with timestamps and log levels
- Rotating log files (max 5MB, 3 backups)

Usage:
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("Signal detected for BBCA.JK")
    logger.warning("Liquidity too low")
    logger.error("Fetch failed", exc_info=True)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── Constants ──────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "bot.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

# ── Format ─────────────────────────────────────────────────
CONSOLE_FMT = "[%(asctime)s] %(levelname)-8s %(name)s │ %(message)s"
FILE_FMT = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# ── Color codes (ANSI) ────────────────────────────────────
_COLORS: dict[str, str] = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Green
    "WARNING":  "\033[33m",   # Yellow
    "ERROR":    "\033[31m",   # Red
    "CRITICAL": "\033[35m",   # Magenta
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """Formatter that adds ANSI color codes for console output."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(record)


# ── Singleton tracker ─────────────────────────────────────
_initialized: bool = False


def _setup_root() -> None:
    """One-time setup of root logger handlers."""
    global _initialized
    if _initialized:
        return

    LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── Console handler ───────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(_ColorFormatter(CONSOLE_FMT, datefmt=DATE_FMT))
    root.addHandler(console_handler)

    # ── File handler (rotating) ───────────────────────────
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FMT, datefmt=DATE_FMT))
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "httpcore", "httpx", "yfinance", "gspread", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Initializes the logging framework on first call.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    _setup_root()
    return logging.getLogger(name)
