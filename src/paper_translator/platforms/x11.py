import time

from PySide6.QtCore import QSocketNotifier, QTimer, Qt
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

from .common import InputAdapter, hotkey_parts
from ..state import SelectionDebouncer


class X11Adapter(InputAdapter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.display = None
        self.notifier = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.debouncer = SelectionDebouncer()
        QApplication.clipboard().dataChanged.connect(self.debouncer.cancel_current)
        self.bindings = {}

    def configure(self, settings):
        super().configure(settings)
        self.debouncer.suspend()
        if self.display:
            self._bind()

    def start(self):
        try:
            from Xlib import display
            self.display = display.Display()
            self.notifier = QSocketNotifier(self.display.fileno(), QSocketNotifier.Type.Read, self)
            self.notifier.activated.connect(self._events)
            self._bind()
            self.timer.start(150)
        except Exception:
            self.status.emit('X11 取词或快捷键连接失败，可用截图按钮和手动输入。')

    def _bind(self):
        from Xlib import X, XK, error
        root = self.display.screen().root
        root.ungrab_key(X.AnyKey, X.AnyModifier)
        self.bindings = {}
        errors = []
        for hotkey, action in [(self.settings.screenshot_hotkey, self.screenshot),
                               (self.settings.toggle_hotkey, self.toggle)]:
            mods, key = hotkey_parts(hotkey)
            flags = sum({'Ctrl': X.ControlMask, 'Alt': X.Mod1Mask, 'Shift': X.ShiftMask, 'Meta': X.Mod4Mask}[m] for m in mods)
            name = key if len(key) > 1 else key.lower()
            code = self.display.keysym_to_keycode(XK.string_to_keysym(name))
            if not code:
                errors.append(hotkey)
                continue
            catches = []
            for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                catch = error.CatchError(error.BadAccess)
                catches.append(catch)
                root.grab_key(code, flags | extra, True, X.GrabModeAsync, X.GrabModeAsync, onerror=catch)
            self.display.sync()
            if any(c.get_error() for c in catches):
                errors.append(hotkey)
            else:
                self.bindings[(code, flags)] = action
        self.status.emit('快捷键冲突，请修改：' + ', '.join(errors) if errors else
                         'Linux X11：自动读取 PRIMARY 选区，快捷键已注册。')

    def _events(self, *args):
        from Xlib import X
        while self.display and self.display.pending_events():
            event = self.display.next_event()
            if event.type == X.KeyPress:
                action = self.bindings.get((event.detail, event.state & ~(X.LockMask | X.Mod2Mask)))
                if action:
                    action.emit()

    def _poll(self):
        from Xlib import X
        if not self.display:
            return
        enabled = self.settings.enabled and self.settings.selection_enabled
        active = QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
        if active:
            self.debouncer.suspend()
            return
        try:
            pointer = self.display.screen().root.query_pointer()
            dragging = bool(pointer.mask & X.Button1Mask)
            text = '' if active or not enabled else QApplication.clipboard().text(QClipboard.Mode.Selection)
            selected = self.debouncer.feed(text, time.monotonic() * 1000,
                                           dragging=dragging, enabled=enabled,
                                           point=(pointer.root_x, pointer.root_y))
            if selected:
                self.selection.emit(selected)
        except Exception:
            pass

    def stop(self):
        self.timer.stop()
        if self.notifier:
            self.notifier.setEnabled(False)
        if self.display:
            self.display.close()
            self.display = None
