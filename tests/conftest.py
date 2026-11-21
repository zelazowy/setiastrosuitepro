"""Wait for real asynchronous renders between the focused preview QA cases."""
import time

import pytest
from PyQt6.QtTest import QTest


def wait_for_preview_workers(timeout=30):
    from setiastro.saspro.thread_keeper import LIVE_THREADS, thread_running
    deadline = time.monotonic() + timeout
    while any(thread_running(thread) for thread in list(LIVE_THREADS)):
        if time.monotonic() > deadline:
            pytest.fail('Preview workers did not finish within 30 seconds')
        QTest.qWait(20)
    QTest.qWait(20)  # Deliver queued result/finished signals.


@pytest.fixture(autouse=True)
def finish_preview_workers(request):
    if request.node.path.name.startswith('test_preview'):
        yield
        wait_for_preview_workers()
    else:
        yield
