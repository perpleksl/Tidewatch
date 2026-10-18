import logging
import subprocess
import sys
import threading
import time

import pytest

from tidewatch.worker.__main__ import run


def test_worker_logs_worker_started(caplog: pytest.LogCaptureFixture) -> None:
    """PER-8 AC5: the worker's log shows "worker started"."""
    stop = threading.Event()
    stop.set()  # return immediately after starting

    with caplog.at_level(logging.INFO, logger="tidewatch.worker"):
        run(stop)

    assert "worker started" in caplog.messages
    assert "worker stopped" in caplog.messages


def test_worker_process_starts_and_stops_on_sigterm() -> None:
    """The real entry point keeps running, then stops cleanly on SIGTERM (as Render sends)."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "tidewatch.worker"],
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(1.5)
        assert proc.poll() is None, "worker exited on its own"
        proc.terminate()
        _, stderr = proc.communicate(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    assert proc.returncode == 0
    assert "worker started" in stderr
    assert "worker stopped" in stderr
