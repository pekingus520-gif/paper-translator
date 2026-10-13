class RequestGate:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.epoch = 0

    def invalidate(self):
        self.epoch += 1

    def issue(self):
        if not self.enabled:
            return None
        self.invalidate()
        return self.epoch

    def accepts(self, token):
        return self.enabled and token is not None and token == self.epoch

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.invalidate()


class SelectionDebouncer:
    def __init__(self, delay_ms=1000):
        self.delay = delay_ms
        self.current = ''
        self.changed_at = 0
        self.emitted = ''
        self.was_enabled = True

    def suspend(self):
        self.was_enabled = False

    def cancel_current(self):
        # A copy action consumes this selection; a new selection may translate.
        self.emitted = self.current

    def feed(self, text, now_ms, dragging=False, enabled=True):
        text = (text or '').strip()
        if not enabled or not self.was_enabled:
            self.current = self.emitted = text
            self.changed_at = now_ms
            self.was_enabled = enabled
            return None
        if dragging:
            # A fresh drag is a new user action even when it selects identical text.
            self.emitted = ''
            self.current = ''
            self.changed_at = now_ms
            return None
        if text != self.current:
            self.current = text
            self.changed_at = now_ms
            if not text:
                self.emitted = ''
            return None
        if text and text != self.emitted and now_ms - self.changed_at >= self.delay:
            self.emitted = text
            return text
        return None
