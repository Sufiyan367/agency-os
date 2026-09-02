import os
import logging
import sys
import re
from typing import Optional
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
SERVICE_LOG_FILE = os.path.join(LOG_DIR, "agency_service.log")

SENSITIVE_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|password|bearer|auth[_-]?token)\s*[:=]\s*["\']?([^"\'\s]+)["\']?'),
]

class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in SENSITIVE_PATTERNS:
                record.msg = pattern.sub(r'\1: [REDACTED]', record.msg)
        return True

def setup_logging(level: str = "INFO", run_id: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger("agency")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if not logger.handlers:
        fmt = f"[%(asctime)s] [{run_id or 'SYSTEM'}] [%(levelname)s] [%(name)s.%(funcName)s]: %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        masking_filter = SecretMaskingFilter()

        # Stream Handler (stdout if available)
        if sys.stdout:
            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setFormatter(formatter)
            stdout_handler.addFilter(masking_filter)
            logger.addHandler(stdout_handler)

        # File Handler (persistent rolling log)
        file_handler = RotatingFileHandler(
            SERVICE_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(masking_filter)
        logger.addHandler(file_handler)

        logger.propagate = False
        
    return logger

logger = setup_logging()
