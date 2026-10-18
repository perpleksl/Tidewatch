"""Background worker entry point.

Run with:  python -m tidewatch.worker
Scheduled jobs are added in later tickets (ingestion framework onward). For now the worker
starts, logs "worker started", and idles until Render (or Ctrl+C) asks it to stop.
"""

import logging
import signal
import threading
from types import FrameType

log = logging.getLogger("tidewatch.worker")


def run(stop: threading.Event) -> None:
    """Run the worker until `stop` is set."""
    log.info("worker started")
    stop.wait()
    log.info("worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        log.info("received signal %s, shutting down", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run(stop)


if __name__ == "__main__":
    main()
