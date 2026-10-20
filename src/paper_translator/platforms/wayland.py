from dataclasses import replace
import time
import uuid

from PySide6.QtCore import QTimer

from .common import InputAdapter, gnome_accelerator
from ..config import atomic_json, config_directory
from ..ipc import socket_name


class WaylandAdapter(InputAdapter):
    def __init__(self, bridge_path=None, socket_path=None, parent=None):
        super().__init__(parent)
        self.bridge_path = bridge_path or config_directory() / 'bridge.json'
        self.socket_path = socket_path or socket_name()
        self.last_heartbeat = 0
        self.bridge_status = ''
        self.result_revision = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._publish)

    def configure(self, settings):
        self.generation = uuid.uuid4().hex
        self.settings = replace(settings)
        self._publish()

    def start(self):
        self.timer.start(2000)
        self._publish()

    def present_result(self):
        self.result_revision += 1
        self._publish()

    def _publish(self, running=True):
        if not hasattr(self, 'settings'):
            return
        atomic_json(self.bridge_path, {
            'running': running, 'timestamp': time.time(), 'socket': self.socket_path,
            'generation': self.generation,
            'result_revision': self.result_revision,
            'enabled': self.settings.enabled and self.settings.selection_enabled,
            'translation_enabled': self.settings.enabled,
            'pin_main': self.settings.main_window_on_top,
            'screenshot': gnome_accelerator(self.settings.screenshot_hotkey),
            'toggle': gnome_accelerator(self.settings.toggle_hotkey),
        })
        if running:
            if time.monotonic() - self.last_heartbeat > 8:
                self.status.emit('Wayland：请安装并启用随附的 GNOME 取词辅助组件；截图按钮和手动输入仍可使用。')
            else:
                self.status.emit(self.bridge_status or 'GNOME Wayland：自动划词与快捷键已连接')

    def receive_heartbeat(self, message):
        self.last_heartbeat = time.monotonic()
        self.bridge_status = message.get('status', '')
        self.status.emit(self.bridge_status or 'GNOME Wayland：自动划词与快捷键已连接')

    def stop(self):
        self.timer.stop()
        self._publish(running=False)
