import argparse
from dataclasses import asdict
import os
from pathlib import Path
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from .capture import RegionCapture
from .config import ConfigStore, atomic_json, config_directory
from .controller import TranslationController
from .ipc import LocalCommandServer, send_command, socket_name
from .zotero import ZoteroBridge
from .ui import MainWindow, ResultWindow, SettingsDialog, StatusToast


def application_icon_path():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    frozen = root / 'paper_translator' / 'assets' / 'paper-translator-icon.png'
    source = Path(__file__).resolve().parent / 'assets' / 'paper-translator-icon.png'
    return frozen if frozen.is_file() else source


def application_icon():
    path = application_icon_path()
    return QIcon(str(path)) if path.is_file() else QIcon()


class DesktopApplication:
    def __init__(self, app, store=None, native_inputs=True):
        self.app = app
        self.store = store or ConfigStore()
        self.settings = self.store.load()
        self.controller = TranslationController(self.settings)
        self.window = MainWindow()
        self.result_window = ResultWindow()
        self.status_toast = StatusToast()
        self.window.refresh(self.settings)
        self.result_window.set_wallpaper(self.settings.wallpaper_path)
        self.result_window.apply_theme(self.settings.color_theme)
        self._apply_opacity(self.settings.window_opacity)
        self.capture_lock = False
        self.capture_token = None
        self._capture_window_opacity = None
        self.native_capture_id = None
        self.native_capture_timer = QTimer()
        self.native_capture_timer.setSingleShot(True)
        self.native_capture_timer.timeout.connect(self._native_capture_timeout)
        QApplication.clipboard().dataChanged.connect(self._native_clipboard_changed)
        self.stopping = False
        self.server = LocalCommandServer()
        config_directory().mkdir(parents=True, exist_ok=True)
        self.server.command.connect(self.command)
        self.server.start()
        self.zotero = ZoteroBridge()
        try:
            self.zotero.start(self.settings)
            self.zotero.selection.connect(self.zotero_selection, Qt.ConnectionType.QueuedConnection)
        except OSError:
            self.zotero = None
            self.window.statusBar().showMessage('Zotero 本地连接未建立，其他翻译入口仍可使用。')
        self.controller.result.connect(self.result_window.display)
        self.controller.source_ready.connect(self.result_window.prepare)
        self.controller.error.connect(self.show_error)
        self.controller.status.connect(self.window.statusBar().showMessage)
        self.controller.finished.connect(self._finished)
        self.window.screenshot.connect(self.screenshot)
        self.window.toggle.connect(self.toggle)
        self.window.settings_requested.connect(self.show_settings)
        self.window.pin_changed.connect(self._pin_main_window)
        self.window.manual.connect(self.manual)
        self.result_window.retry.connect(self.retry)

        self.wayland = sys.platform.startswith('linux') and os.environ.get('XDG_SESSION_TYPE') == 'wayland'
        if self.wayland:
            from .capture import PortalCapture
            self.capture = PortalCapture()
            self.capture.path_ready.connect(self._portal_image)
        else:
            self.capture = RegionCapture()
            self.capture.captured.connect(self._image)
        self.capture.error.connect(self._capture_error)
        self.capture.cancelled.connect(self._capture_cancel)

        self.adapter = None
        if native_inputs:
            self._start_inputs()
        self._tray()
        self.app.aboutToQuit.connect(self.shutdown)
        if self.store.warning:
            self.window.statusBar().showMessage(self.store.warning)

    def _start_inputs(self):
        if sys.platform == 'win32':
            from .platforms.windows import WindowsAdapter
            self.adapter = WindowsAdapter()
        elif self.wayland:
            from .platforms.wayland import WaylandAdapter
            self.adapter = WaylandAdapter()
        elif sys.platform.startswith('linux'):
            from .platforms.x11 import X11Adapter
            self.adapter = X11Adapter()
        else:
            self.window.platform_status.setText('当前系统未实现自动划词与全局快捷键，可用截图按钮和手动输入。')
            return
        self.adapter.selection.connect(self.selection)
        self.adapter.screenshot.connect(self.screenshot)
        self.adapter.toggle.connect(self.toggle)
        self.adapter.status.connect(self.window.platform_status.setText)
        try:
            self.adapter.configure(self.settings)
            self.adapter.start()
        except Exception:
            self.window.platform_status.setText('桌面自动取词服务启动失败，可用截图按钮和手动输入。')

    def _tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # Keep the frameless wallpaper canvas edge-to-edge. Without a tray,
            # the close control exits instead of hiding an unreachable process.
            self.window.allow_quit = True
            return
        icon = self.app.windowIcon()
        if icon.isNull():
            icon = self.app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        self.tray = QSystemTrayIcon(icon)
        menu = QMenu()
        for label, callback in [('打开主窗口', self.show), ('截图翻译', self.screenshot),
                                ('暂停 / 恢复', self.toggle), ('设置', self.show_settings), ('退出', self.quit)]:
            action = menu.addAction(label)
            action.triggered.connect(callback)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.setToolTip('Paper Translator')
        self.tray.show()
        self.window.can_hide_to_tray = True

    def show(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _apply_theme(self, name):
        self.window.apply_theme(name)
        self.result_window.apply_theme(name)

    def _apply_wallpaper(self, path):
        self.window.set_wallpaper(path)
        self.result_window.set_wallpaper(path)

    def _apply_opacity(self, value):
        opacity = max(30, min(100, int(value))) / 100
        self.window.setWindowOpacity(opacity)
        self.result_window.setWindowOpacity(opacity)

    def _pin_main_window(self, enabled):
        self.settings.main_window_on_top = enabled
        if self.adapter:
            self.adapter.configure(self.settings)
        self._save_preferences()

    def command(self, message):
        name = message['command']
        if name == 'selection':
            if self.adapter and hasattr(self.adapter, 'generation') and message.get('generation') != self.adapter.generation:
                return
            self.selection(message['text'])
        elif name == 'screenshot':
            self.screenshot()
        elif name == 'screenshot_native':
            self.screenshot_native(message.get('capture_id'))
        elif name == 'screenshot_file':
            self._native_file(message.get('capture_id'), message.get('path'))
        elif name == 'screenshot_cancel':
            self._native_cancel(message.get('capture_id'))
        elif name == 'toggle':
            self.toggle()
        elif name == 'show':
            self.show()
        elif name == 'bridge' and self.adapter and hasattr(self.adapter, 'receive_heartbeat'):
            self.adapter.receive_heartbeat(message)

    def zotero_selection(self, message):
        if not self.zotero or message.get('generation') != self.zotero.generation:
            return
        if not self.capture_lock and self.settings.enabled and self.settings.selection_enabled:
            context = message.get('context', '') if self.settings.mode == 'paper' else ''
            self.controller.submit_text(message['text'], context=context)

    def retry(self, text):
        if self.settings.enabled:
            self.controller.submit_text(text, context=self.controller.last_context)

    def selection(self, text):
        if not self.capture_lock and self.settings.selection_enabled and self.settings.enabled:
            self.controller.submit_text(text)

    def manual(self, text):
        if not self.settings.enabled:
            self.window.statusBar().showMessage('翻译已暂停，请先恢复')
            return
        if not text.strip():
            self.window.statusBar().showMessage('请先输入文字')
            return
        self.capture_lock = False
        self.controller.submit_text(text)

    def screenshot(self):
        if not self.settings.enabled or self.capture_lock:
            return
        self.controller.gate.invalidate()
        self.controller.pending = None
        self.capture_lock = True
        if self.wayland:
            # The portal refuses permission dialogs from an unfocused app.
            # Keep a transparent window focused while the shell chooses an area.
            self._capture_window_opacity = self.window.windowOpacity()
            self.window.setWindowOpacity(0.0)
            self.window.showNormal()
            self.window.raise_()
            self.window.activateWindow()
        else:
            self.window.showMinimized()
        self.window.statusBar().showMessage('请选择截图区域，取消可按 Esc')
        QTimer.singleShot(350 if self.wayland else 180, self._start_capture)

    def screenshot_native(self, capture_id):
        """GNOME Shell captures the region without a portal focus dialog."""
        if not self.wayland or not self.settings.enabled or self.capture_lock or not capture_id:
            return
        self.controller.gate.invalidate()
        self.controller.pending = None
        self.capture_lock = True
        self.capture_token = None
        self.native_capture_id = capture_id
        self.window.showMinimized()
        self.native_capture_timer.start(60000)

    def _native_file(self, capture_id, path):
        if not self.native_capture_id or capture_id != self.native_capture_id or not path:
            return
        image = QImage(path)
        if image.isNull():
            self.native_capture_id = None
            self.native_capture_timer.stop()
            self._capture_error('GNOME 截图文件无法读取')
            return
        self.native_capture_id = None
        self.native_capture_timer.stop()
        self._image(image)

    def _native_clipboard_changed(self):
        # GNOME also puts screenshots on the clipboard. This covers desktops
        # where the saved screenshot path is unavailable to the Qt process.
        if not self.native_capture_id:
            return
        image = QApplication.clipboard().image()
        if image.isNull():
            return
        self.native_capture_id = None
        self.native_capture_timer.stop()
        self._image(image)

    def _native_cancel(self, capture_id):
        if capture_id != self.native_capture_id:
            return
        self.native_capture_id = None
        self.native_capture_timer.stop()
        self._capture_cancel()
        self.window.showNormal()

    def _native_capture_timeout(self):
        if self.native_capture_id:
            self.native_capture_id = None
            self.capture_lock = False
            self.capture_token = None
            self.window.showNormal()

    def _restore_capture_window(self):
        if self._capture_window_opacity is not None:
            self.window.setWindowOpacity(self._capture_window_opacity)
            self._capture_window_opacity = None

    def _start_capture(self):
        if self.capture_lock and self.settings.enabled:
            self.capture.start()

    def _portal_image(self, path):
        self._restore_capture_window()
        self._image(QImage(path))

    def _image(self, image):
        if not self.capture_lock or not self.settings.enabled:
            return
        self.capture_token = self.controller.submit_image(image)
        if self.capture_token is None:
            self.capture_lock = False

    def _finished(self, token):
        if token == self.capture_token:
            self.capture_lock = False
            self.capture_token = None

    def _capture_cancel(self):
        self.native_capture_id = None
        self.native_capture_timer.stop()
        self._restore_capture_window()
        self.capture_lock = False
        self.capture_token = None
        self.window.statusBar().showMessage('截图已取消')

    def _capture_error(self, error):
        self._restore_capture_window()
        self.capture_lock = False
        self.capture_token = None
        if self.settings.enabled:
            self.show_error(error)

    def show_error(self, message):
        self.window.statusBar().showMessage(message)
        if self.settings.enabled:
            self.result_window.show_error(message)

    def toggle(self):
        self.native_capture_id = None
        self.native_capture_timer.stop()
        self._restore_capture_window()
        enabled = not self.settings.enabled
        self.controller.set_enabled(enabled)
        self.capture.cancel()
        self.capture_lock = False
        self.capture_token = None
        self.window.refresh(self.settings)
        if self.adapter:
            self.adapter.configure(self.settings)
        if self.zotero:
            self.zotero.configure(self.settings)
        self._save_preferences()
        self.status_toast.show_state(enabled, self.settings.color_theme,
                                     self.settings.wallpaper_path, self.settings.window_opacity)

    def _save_preferences(self):
        values = asdict(self.settings)
        for name in self.store.secret_names:
            values.pop(name)
        try:
            atomic_json(self.store.path, values)
        except OSError:
            self.window.statusBar().showMessage('无法保存开关设置，请检查配置目录权限')

    def show_settings(self):
        dialog = SettingsDialog(self.settings, self.window)
        original_theme = self.settings.color_theme
        original_opacity = self.settings.window_opacity
        original_wallpaper = self.settings.wallpaper_path
        dialog.theme_changed.connect(self._apply_theme)
        dialog.wallpaper_changed.connect(self._apply_wallpaper)
        dialog.opacity_changed.connect(self._apply_opacity)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._apply_wallpaper(original_wallpaper)
            self._apply_theme(original_theme)
            self._apply_opacity(original_opacity)
            return
        settings = dialog.values()
        try:
            warning = self.store.save(settings)
        except (OSError, ValueError) as exc:
            self._apply_wallpaper(original_wallpaper)
            self._apply_theme(original_theme)
            self._apply_opacity(original_opacity)
            QMessageBox.warning(self.window, '保存失败', str(exc))
            return
        self.capture.cancel()
        self.native_capture_id = None
        self.native_capture_timer.stop()
        self.capture_lock = False
        self.capture_token = None
        self.settings = settings
        if self.zotero:
            self.zotero.configure(settings)
        self.controller.apply_settings(settings)
        self.window.refresh(settings)
        self.result_window.set_wallpaper(settings.wallpaper_path)
        self.result_window.apply_theme(settings.color_theme)
        self._apply_opacity(settings.window_opacity)
        if self.adapter:
            self.adapter.configure(settings)
        if warning:
            QMessageBox.information(self.window, '密钥保存提示', warning)

    def shutdown(self):
        if self.stopping:
            return
        self.stopping = True
        self.native_capture_id = None
        self.native_capture_timer.stop()
        self.window.allow_quit = True
        self.controller.set_enabled(False)
        self.capture.cancel()
        if self.adapter:
            self.adapter.stop()
        self.server.close()
        if self.zotero:
            self.zotero.close()
        self.result_window.hide()
        self.status_toast.hide()
        if self.tray:
            self.tray.hide()
        self.controller.pool.waitForDone()

    def quit(self):
        self.shutdown()
        self.app.quit()


def main(argv=None):
    import multiprocessing
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description='划词与截图翻译器')
    parser.add_argument('--screenshot', action='store_true')
    parser.add_argument('--toggle', action='store_true')
    parser.add_argument('--no-inputs', action='store_true', help='禁用原生输入适配，供诊断使用')
    parser.add_argument('--smoke-test', action='store_true', help='启动界面后自动退出，不调用翻译 API')
    args = parser.parse_args(argv)
    QApplication.setApplicationName('PaperTranslator')
    QApplication.setDesktopFileName('io.github.papertranslator.App')
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(application_icon())
    app.setQuitOnLastWindowClosed(False)
    command = {'command': 'toggle' if args.toggle else 'screenshot' if args.screenshot else 'show'}
    if send_command(socket_name(), command):
        return 0
    try:
        desktop = DesktopApplication(app, native_inputs=not args.no_inputs)
    except RuntimeError as exc:
        QMessageBox.warning(None, '无法启动', str(exc))
        return 1
    desktop.show()
    if args.screenshot:
        QTimer.singleShot(300, desktop.screenshot)
    if args.toggle:
        desktop.toggle()
    if args.smoke_test:
        QTimer.singleShot(800, desktop.quit)
    return app.exec()
