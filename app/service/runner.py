import os
import sys
import time
import signal
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
try:
    os.chdir(BASE_DIR)
except Exception:
    pass

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "agency_service.log")

# When executed under pythonw.exe, sys.stdout and sys.stderr are None.
# Redirect them immediately to LOG_FILE so nothing is lost and no stream crashes occur.
if sys.stdout is None:
    sys.stdout = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)

# Setup persistent rotating service logger
logger = logging.getLogger("agency_service")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s] [SERVICE] [%(levelname)s]: %(message)s", "%Y-%m-%d %H:%M:%S")

file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

if sys.stdout and hasattr(sys.stdout, "write"):
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

keep_running = True

def handle_shutdown(signum, frame):
    global keep_running
    logger.info(f"Received termination signal ({signum}). Initiating graceful agency shutdown...")
    keep_running = False

def run_service_supervisor():
    """
    Persistent Windows background service supervisor.
    Spawns and monitors the unified agency server (API, Dashboard, and Worker).
    Automatically restarts after any crash or unexpected termination.
    """
    global keep_running
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, handle_shutdown)

    logger.info("==================================================================")
    logger.info("Autonomous B2B Lead-Gen & Sales Agency — Windows Background Service")
    logger.info(f"Root Directory: {BASE_DIR}")
    logger.info(f"Log File: {LOG_FILE}")
    logger.info("==================================================================")

    import uvicorn

    restart_count = 0
    while keep_running:
        try:
            logger.info("Starting Agency Server (FastAPI + Persistent Worker) on http://0.0.0.0:8000...")
            config = uvicorn.Config(
                "app.api.app:app",
                host="0.0.0.0",
                port=8000,
                log_level="info",
                access_log=False,
                timeout_keep_alive=30
            )
            server = uvicorn.Server(config)
            server.run()

            if not keep_running:
                logger.info("Service shutdown completed cleanly.")
                break
            else:
                logger.warning("Uvicorn server exited unexpectedly. Preparing automatic restart...")
        except Exception as e:
            logger.error(f"Agency service encountered an error: {e}", exc_info=True)

        if keep_running:
            restart_count += 1
            backoff_delay = min(5 * restart_count, 30)
            logger.info(f"Auto-restarting agency service in {backoff_delay} seconds (Crash Recovery Attempt #{restart_count})...")
            time.sleep(backoff_delay)

if __name__ == "__main__":
    run_service_supervisor()
