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
    def __init__(self, delay_ms=1000, minimum_drag=8):
        self.delay = delay_ms
        self.minimum_drag_squared = minimum_drag * minimum_drag
        self.current = ''
        self.drag = None
        self.awaiting_until = 0
        self.pending = ''
        self.pending_since = 0
        self.copied = ''
        self.copy_blocked = False
        self.priming = True
        self.was_enabled = True

    def suspend(self):
        self.priming = True
        self.drag = None
        self.pending = ''
        self.awaiting_until = 0

    def cancel_current(self):
        self.copy_blocked = True
        self.copied = self.pending or self.current
        self.pending = ''
        self.awaiting_until = 0

    def feed(self, text, now_ms, dragging=False, enabled=True, point=None):
        text = (text or '').strip()
        if not enabled:
            self.current = text
            self.suspend()
            self.copied = ''
            return None
        if self.priming and not dragging:
            self.current = text
            self.priming = False
            return None
        if dragging:
            if self.drag is None:
                self.drag = {'baseline': self.current, 'start': point, 'moved': False}
                self.copy_blocked = False
                self.pending = ''
                self.awaiting_until = 0
            elif point is not None and self.drag['start'] is not None:
                dx = point[0] - self.drag['start'][0]
                dy = point[1] - self.drag['start'][1]
                if dx * dx + dy * dy >= self.minimum_drag_squared:
                    self.drag['moved'] = True
            return None
        if self.drag is not None:
            gesture = self.drag
            self.drag = None
            self.awaiting_until = now_ms + 500 if gesture['moved'] and not self.copy_blocked else 0
            self.pending = ''
            if text and text != gesture['baseline'] and text != self.copied and gesture['moved'] and not self.copy_blocked:
                self.pending = text
                self.pending_since = now_ms
                self.awaiting_until = 0
                self.copied = ''
            self.current = text
            return None
        if text != self.current:
            if self.awaiting_until and now_ms <= self.awaiting_until and text and text != self.copied and not self.copy_blocked:
                self.pending = text
                self.pending_since = now_ms
                self.copied = ''
            else:
                self.pending = ''
            self.current = text
            self.awaiting_until = 0
            return None
        if self.awaiting_until and now_ms > self.awaiting_until:
            self.awaiting_until = 0
        if self.pending and text == self.pending and now_ms - self.pending_since >= self.delay:
            selected = self.pending
            self.pending = ''
            return selected
        return None
