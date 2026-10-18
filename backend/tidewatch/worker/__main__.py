"""Background worker entry point.

Run with:  python -m tidewatch.worker
Every TICK_SECONDS the worker checks which data sources are due (intervals come from
Settings) and runs them. Errors are logged and never stop the loop. It stops cleanly when
Render (or Ctrl+C) asks.
"""

import logging
import signal
import threading
from functools import lru_cache
from types import FrameType

from sqlalchemy.orm import Session, sessionmaker

from tidewatch.db.session import make_engine
from tidewatch.ingestion.registry import registered_adapters
from tidewatch.ingestion.runner import run_due

log = logging.getLogger("tidewatch.worker")

#: How often the worker checks for due sources (technical; intervals come from Settings).
TICK_SECONDS = 15.0


@lru_cache(maxsize=1)
def _default_sessions() -> sessionmaker[Session]:
    return sessionmaker(make_engine())


def tick(sessions: sessionmaker[Session] | None) -> None:
    """One scheduler check. Never raises: a broken check must not stop the worker."""
    try:
        run_due(sessions or _default_sessions(), registered_adapters())
    except Exception:
        log.exception("scheduler check failed")


def run(stop: threading.Event, sessions: sessionmaker[Session] | None = None) -> None:
    """Run the worker until `stop` is set."""
    log.info("worker started")
    if not stop.is_set():
        tick(sessions)
    while not stop.wait(TICK_SECONDS):
        tick(sessions)
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
