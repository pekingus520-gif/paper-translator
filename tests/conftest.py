import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session', autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def spin(qapp):
    def wait(predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            qapp.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        assert predicate(), 'Qt event condition timed out'
    return wait
