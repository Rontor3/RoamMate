"""
Shared logger for RoamMate. Use get_logger(__name__) in every module.
Files in tools/ (MCP server processes) cannot import from app/ — use logging.getLogger(__name__) directly.
"""
import logging
import os
import sys

os.makedirs("logs", exist_ok=True)

_handler_added = False

def get_logger(name: str) -> logging.Logger:
    global _handler_added
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)

    if not _handler_added:
        fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # File handler
        fh = logging.FileHandler("logs/roammate.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)

        # Attach to the "app" namespace so Uvicorn doesn't swallow or duplicate logs
        app_logger = logging.getLogger("app")
        app_logger.setLevel(logging.DEBUG)
        app_logger.addHandler(fh)
        app_logger.addHandler(ch)
        app_logger.propagate = False
        
        _handler_added = True

    return log

# Backwards-compatible alias used by legacy modules
logger = get_logger("roammate")