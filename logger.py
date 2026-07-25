"""
Thread-safe logging configuration for Bulk Business Search & Export Pro.
"""

import logging
from logging.handlers import RotatingFileHandler
from config import LOG_PATH

def setup_logger():
    """Initializes and returns the root logger configuration."""
    logger = logging.getLogger("BulkBusinessSearch")
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger

    # Formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(threadName)s] %(filename)s:%(lineno)d: %(message)s"
    )

    # File Handler (rotating at 5MB, keep 3 backups)
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Create the logger instance
logger = setup_logger()
