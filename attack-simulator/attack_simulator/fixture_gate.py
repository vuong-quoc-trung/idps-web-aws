"""One-shot, run-bound operator confirmation. No Defender calls."""
import threading
import time

class FixtureGate:
    def __init__(self):
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.pending = False
        self.accepted = False

    def open(self):
        with self.lock:
            self.ready.clear()
            self.accepted = False
            self.pending = True

    def confirm(self, accepted):
        with self.lock:
            if not self.pending: return False
            self.pending = False
            self.accepted = accepted is True
            self.ready.set()
            return True

    def wait(self, seconds, stop):
        deadline = time.monotonic() + max(0, seconds)
        try:
            while not stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0: return False
                if self.ready.wait(min(.1, remaining)):
                    return self.accepted and not stop.is_set()
            return False
        finally:
            with self.lock: self.pending = False
