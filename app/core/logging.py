import logging
import sys
import re
from typing import Optional

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
        handler = logging.StreamHandler(sys.stdout)
        fmt = f"[%(asctime)s] [{run_id or 'SYSTEM'}] [%(levelname)s] [%(name)s.%(funcName)s]: %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        handler.addFilter(SecretMaskingFilter())
        logger.addHandler(handler)
        logger.propagate = False
        
    return logger

logger = setup_logging()
