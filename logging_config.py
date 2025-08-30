import logging
import logging.handlers
from pathlib import Path
from config import DEBUG_MODE

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Configure logging
def setup_logging():
    """Setup logging configuration for the Gmail API service"""

    # Create logger
    logger = logging.getLogger('gmail_api')
    logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

    # File handler (rotating file handler)
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/gmail_api.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

# Global logger instance
logger = setup_logging()

# Convenience functions for easy logging
def log_info(message):
    """Log an info message"""
    logger.info(message)

def log_warning(message):
    """Log a warning message"""
    logger.warning(message)

def log_error(message):
    """Log an error message"""
    logger.error(message)

def log_debug(message):
    """Log a debug message"""
    logger.debug(message)

def log_critical(message):
    """Log a critical message"""
    logger.critical(message)
