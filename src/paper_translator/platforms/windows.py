"""Windows hotkeys + non-destructive UI Automation selection polling."""
import ctypes
from ctypes import wintypes
import os
import multiprocessing
import time

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtWidgets import QApplication

from .common import InputAdapter, hotkey_parts
from .process import stop_process
from ..state import SelectionDebouncer


def selection_process(connection, parent_pid):
    try:
        import uiautomation as auto
        debouncer = SelectionDebouncer()
        debouncer.suspend()
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
        clipboard_sequence = user32.GetClipboardSequenceNumber()
        enabled, generation = False, 0
        while True:
            while connection.poll():
                config = connection.recv()
                if config.get('stop'):
                    return
                enabled = config['enabled']
                generation = config['generation']
                debouncer.suspend()
            text = ''
            dragging = bool(user32.GetAsyncKeyState(1) & 0x8000)
            cursor = wintypes.POINT()
            point = (cursor.x, cursor.y) if user32.GetCursorPos(ctypes.byref(cursor)) else None
            if enabled and not dragging:
                try:
                    hwnd = user32.GetForegroundWindow()
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == parent_pid:
                        debouncer.suspend()
                        time.sleep(0.15)
                        continue
                    if pid.value:
                        control = auto.GetFocusedControl()
                        for _ in range(5):
                            if not control or control.IsPassword:
                                break
                            pattern = control.GetPattern(auto.PatternId.TextPattern)
                            if pattern:
                                text = '\n'.join(r.GetText(10001) for r in pattern.GetSelection())
                                break
                            control = control.GetParentControl()
                except Exception:
                    text = ''
            selected = debouncer.feed(text, time.monotonic() * 1000, dragging=dragging,
                                      enabled=enabled, point=point)
            current_sequence = user32.GetClipboardSequenceNumber()
            if current_sequence != clipboard_sequence:
                if debouncer.current and not dragging:
                    debouncer.cancel_current()
                    selected = None
                clipboard_sequence = current_sequence
            if selected:
                connection.send({'text': selected, 'generation': generation})
            time.sleep(0.15)
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        try:
            connection.send({'error': 'Windows 取词服务不可用，请检查 uiautomation；不支持的应用可用截图翻译。'})
        except OSError:
            pass
    finally:
        connection.close()


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, adapter):
        super().__init__()
        self.adapter = adapter

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312:
            if msg.wParam == 7101:
                self.adapter.screenshot.emit()
                return True, 0
            if msg.wParam == 7102:
                self.adapter.toggle.emit()
                return True, 0
        return False, 0


class WindowsAdapter(InputAdapter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter = HotkeyFilter(self)
        self.worker = None
        self.connection = None
        self.generation = 0
        self.poller = QTimer(self)
        self.poller.timeout.connect(self._drain)
        self.registered = []
        self.errors = []

    def configure(self, settings):
        super().configure(settings)
        user32 = ctypes.windll.user32
        for ident in self.registered:
            user32.UnregisterHotKey(None, ident)
        self.registered = []
        self.errors = []
        for ident, hotkey in [(7101, settings.screenshot_hotkey), (7102, settings.toggle_hotkey)]:
            mods, key = hotkey_parts(hotkey)
            flags = 0x4000 | sum({'Alt': 1, 'Ctrl': 2, 'Shift': 4, 'Meta': 8}[m] for m in mods)
            vk = 0x70 + int(key[1:]) - 1 if len(key) > 1 and key.startswith('F') else ord(key)
            if user32.RegisterHotKey(None, ident, flags, vk):
                self.registered.append(ident)
            else:
                self.errors.append(hotkey)
        self.generation += 1
        self._send_config()
        self.status.emit('快捷键冲突，请修改：' + ', '.join(self.errors) if self.errors else
                         'Windows：快捷键已注册，UI Automation 自动读取支持应用的选区。')

    def start(self):
        QApplication.instance().installNativeEventFilter(self.filter)
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.worker = context.Process(target=selection_process, args=(child, os.getpid()), daemon=True)
        self.worker.start()
        child.close()
        self._send_config()
        self.poller.start(100)

    def _send_config(self):
        if self.connection:
            try:
                self.connection.send({'enabled': self.settings.enabled and self.settings.selection_enabled,
                                      'generation': self.generation})
            except OSError:
                pass

    def _drain(self):
        try:
            while self.connection and self.connection.poll():
                message = self.connection.recv()
                if message.get('error'):
                    self.status.emit(message['error'])
                elif message.get('generation') == self.generation and self.settings.enabled and self.settings.selection_enabled:
                    self.selection.emit(message['text'])
        except (OSError, EOFError):
            self.poller.stop()

    def stop(self):
        QApplication.instance().removeNativeEventFilter(self.filter)
        for ident in self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, ident)
        self.registered = []
        self.poller.stop()
        stop_process(self.worker, self.connection)
        self.worker = self.connection = None
