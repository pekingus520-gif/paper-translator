from dataclasses import replace
import json
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QAbstractAnimation, QPoint, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFrame, QGroupBox, QLabel, QMenuBar, QPushButton, QSplitter, QSystemTrayIcon

from paper_translator.config import ConfigStore, Settings
from paper_translator.controller import TranslationController
from paper_translator.providers import TranslationResult
from paper_translator.ocr import OCR, OCRError
from paper_translator.ipc import LocalCommandServer
from paper_translator.ui import MainWindow, SettingsDialog, ResultWindow, StatusToast, THEMES, blend_palette, result_palette, theme_colors
from paper_translator.capture import RegionOverlay, PortalCapture


class BlockingTranslator:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def translate(self, text, settings, cancelled=lambda: False):
        self.calls.append(text)
        self.started.set()
        self.release.wait(2)
        return TranslationResult(text, 'translated ' + text)


def test_pause_discards_inflight_result(qapp, spin):
    translator = BlockingTranslator()
    c = TranslationController(Settings(), translator=translator)
    results = []
    c.result.connect(results.append)
    c.submit_text('old')
    spin(translator.started.is_set)
    c.set_enabled(False)
    translator.release.set()
    spin(lambda: not c.busy)
    assert not results
    c.submit_text('disabled')
    assert translator.calls == ['old']


def test_only_latest_pending_selection_is_translated(qapp, spin):
    translator = BlockingTranslator()
    c = TranslationController(Settings(), translator=translator)
    results = []
    c.result.connect(results.append)
    c.submit_text('one')
    spin(translator.started.is_set)
    c.submit_text('two')
    c.submit_text('three')
    translator.release.set()
    spin(lambda: not c.busy and not c.pending)
    assert translator.calls == ['one', 'three']
    assert [r.source for r in results] == ['three']


def test_settings_change_discards_old_response(qapp, spin):
    t = BlockingTranslator()
    c = TranslationController(Settings(), translator=t)
    results = []
    c.result.connect(results.append)
    c.submit_text('old')
    spin(t.started.is_set)
    c.apply_settings(replace(c.settings, mode='paper'))
    t.release.set()
    spin(lambda: not c.busy)
    assert not results


def test_source_is_available_to_edit_even_if_api_fails(qapp, spin):
    from paper_translator.providers import TranslationError
    class FailingTranslator:
        def translate(self, text, settings, cancelled=lambda: False):
            raise TranslationError('API failed')
    controller = TranslationController(Settings(), translator=FailingTranslator())
    sources, errors = [], []
    controller.source_ready.connect(sources.append)
    controller.error.connect(errors.append)
    controller.submit_text('recognized text')
    spin(lambda: bool(errors))
    assert sources == ['recognized text']


def test_old_bridge_command_is_ignored_after_pause_resume():
    from types import SimpleNamespace
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.adapter = SimpleNamespace(generation='new-generation')
    selected = []
    desktop.selection = selected.append
    desktop.command({'command': 'selection', 'text': 'stale', 'generation': 'old-generation'})
    desktop.command({'command': 'selection', 'text': 'current', 'generation': 'new-generation'})
    assert selected == ['current']


def test_ipc_accepts_one_bounded_command_and_rejects_bad_input(qapp, spin, tmp_path):
    received = []
    server = LocalCommandServer(str(tmp_path / 'test.sock'))
    server.command.connect(received.append)
    server.start()
    clients = []
    for payload in [b'{"command":"selection","text":"sentence"}\n',
                    b'{"command":"screenshot_native","capture_id":"capture-one"}\n',
                    b'{"command":"screenshot_file","capture_id":"capture-one","path":"/tmp/shot.png"}\n',
                    b'{"command":"screenshot_file","capture_id":"capture-one","path":45}\n',
                    b'{"command":"unknown"}\n', b'{"command":"selection","text":45}\n',
                    b'x' * 70000 + b'\n']:
        s = QLocalSocket()
        clients.append(s)
        s.connectToServer(server.name)
        assert s.waitForConnected(1000)
        s.write(payload)
        s.flush()
    spin(lambda: len(received) == 3)
    for _ in range(5):
        qapp.processEvents()
    assert received == [{'command': 'selection', 'text': 'sentence'},
                        {'command': 'screenshot_native', 'capture_id': 'capture-one'},
                        {'command': 'screenshot_file', 'capture_id': 'capture-one', 'path': '/tmp/shot.png'}]
    for s in clients:
        s.abort()
    server.close()


def test_second_instance_does_not_remove_active_server(qapp, tmp_path):
    name = str(tmp_path / 'one.sock')
    one = LocalCommandServer(name)
    one.start()
    with pytest.raises(RuntimeError):
        LocalCommandServer(name).start()
    probe = QLocalSocket()
    probe.connectToServer(name)
    assert probe.waitForConnected(1000)
    probe.abort()
    one.close()


def test_ocr_missing_program_is_actionable(tmp_path):
    with pytest.raises(OCRError, match='Tesseract'):
        OCR(executable=str(tmp_path / 'missing')).recognize(tmp_path / 'image.png')


def test_bundled_ocr_is_found_without_system_install(monkeypatch, tmp_path):
    import sys
    binary = tmp_path / 'ocr' / 'tesseract'
    binary.parent.mkdir()
    binary.touch()
    (binary.parent / 'tessdata').mkdir()
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setattr('paper_translator.ocr.shutil.which', lambda name: None)
    ocr = OCR()
    assert Path(ocr.executable) == binary
    assert Path(ocr.tessdata) == binary.parent / 'tessdata'


def test_ocr_real_process_boundary_and_blank_text(tmp_path):
    import os
    if os.name == 'nt':
        pytest.skip('POSIX test executable')
    binary = tmp_path / 'ocr'
    binary.write_text('#!/bin/sh\nprintf "Attention mechanism\\n"\n')
    binary.chmod(0o700)
    image = tmp_path / 'image.png'
    QImage(100, 100, QImage.Format.Format_RGB32).save(str(image))
    assert OCR(executable=str(binary)).recognize(image) == 'Attention mechanism'
    binary.write_text('#!/bin/sh\nexit 0\n')
    with pytest.raises(OCRError, match='文字'):
        OCR(executable=str(binary)).recognize(image)


def test_settings_roundtrip_and_hotkeys_are_editable(qapp):
    s = Settings(mode='paper', discipline='物理', screenshot_hotkey='Ctrl+Shift+S')
    dialog = SettingsDialog(s)
    result = dialog.values()
    assert result.mode == 'paper'
    assert result.discipline == '物理'
    assert result.screenshot_hotkey == 'Ctrl+Shift+S'
    assert result.toggle_hotkey == 'Ctrl+Alt+T'
    assert not {'discipline', 'source_language', 'target_language'} & dialog.inputs.keys()
    visible_text = ' '.join(label.text() for label in dialog.findChildren(QLabel))
    assert '论文研究领域' not in visible_text
    assert '源语言代码' not in visible_text
    assert '快捷键示例' not in visible_text
    dialog.close()


def test_appearance_settings_copy_wallpaper_and_roundtrip(tmp_path, qapp):
    source = tmp_path / 'source.png'
    image = QImage(80, 40, QImage.Format.Format_RGB32)
    image.fill(QColor('#4f46e5'))
    assert image.save(str(source))

    class Ring:
        def get_password(self, service, name): return ''
        def set_password(self, service, name, value): pass
        def delete_password(self, service, name): pass

    store = ConfigStore(tmp_path / 'profile/settings.json', Ring())
    settings = Settings(wallpaper_path=str(source), window_opacity=64, color_theme='light')
    store.save(settings)

    installed = tmp_path / 'profile/wallpaper.png'
    assert settings.wallpaper_path == str(installed)
    assert installed.read_bytes() == source.read_bytes()
    loaded = store.load()
    assert loaded.wallpaper_path == str(installed)
    assert loaded.window_opacity == 64
    assert loaded.color_theme == 'light'


def test_legacy_wallpaper_opacity_migrates_to_window_opacity(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'wallpaper_opacity': 58}), encoding='utf-8')
    loaded = ConfigStore(path, keyring_backend=None).load()
    assert loaded.window_opacity == 58


def test_main_window_is_minimal_and_ctrl_enter_translates(qapp):
    window = MainWindow()
    window.refresh(Settings())
    window.show()
    qapp.processEvents()
    button_texts = [button.text() for button in window.findChildren(QPushButton) if button.isVisible()]
    visible_labels = ' '.join(label.text() for label in window.findChildren(QLabel) if label.isVisible())
    assert '设置' in button_texts
    assert not {'截图翻译', '暂停 / 恢复', '翻译输入文字'} & set(button_texts)
    assert '已启用' not in visible_labels
    assert '已连接' not in visible_labels
    assert not window.statusBar().isVisible()

    submitted = []
    window.manual.connect(submitted.append)
    window.input.setPlainText('manual translation')
    window.input.setFocus()
    QTest.keyClick(window.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert submitted == ['manual translation']
    window.allow_quit = True
    window.close()


def test_translation_switch_toast_updates_immediately_and_resets_timeout(qapp):
    toast = StatusToast()
    assert toast.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert toast.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    toast.show_state(True, 'dark')
    assert toast.isVisible()
    assert toast.message.text() == '翻译已开启'
    assert toast.dismiss_timer.isActive()
    toast.show_state(False, 'light')
    assert toast.message.text() == '翻译已暂停'
    assert toast.dismiss_timer.remainingTime() > 1500
    toast.dismiss_timer.stop()
    toast.hide()


def test_toggle_updates_toast_with_new_state(qapp):
    from types import SimpleNamespace
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.settings = Settings(enabled=True)
    desktop.native_capture_id = None
    desktop.native_capture_timer = SimpleNamespace(stop=lambda: None)
    desktop._restore_capture_window = lambda: None
    desktop.controller = SimpleNamespace(set_enabled=lambda enabled: setattr(desktop.settings, 'enabled', enabled))
    desktop.capture = SimpleNamespace(cancel=lambda: None)
    desktop.window = SimpleNamespace(refresh=lambda settings: None)
    desktop.adapter = None
    desktop.zotero = None
    desktop._save_preferences = lambda: None
    states = []
    desktop.status_toast = SimpleNamespace(show_state=lambda *args: states.append(args))
    desktop.toggle()
    desktop.toggle()
    assert [state[0] for state in states] == [False, True]


def test_application_icon_is_transparent_and_uses_project_asset():
    from paper_translator.app import application_icon, application_icon_path
    path = application_icon_path()
    assert path.name == 'paper-translator-icon.png'
    image = QImage(str(path))
    assert not image.isNull()
    assert image.hasAlphaChannel()
    assert image.pixelColor(0, 0).alpha() == 0
    assert not application_icon().isNull()


def test_shortcut_icon_preserves_supplied_dark_background():
    from paper_translator.ui import application_asset_path
    image = QImage(str(application_asset_path('paper-translator-shortcut.png')))
    assert not image.isNull()
    assert image.pixelColor(0, 0).red() < 100
    assert image.pixelColor(image.width() // 2, image.height() // 5).red() > 200


def test_main_title_bar_shows_the_application_logo(qapp):
    window = MainWindow()
    logo = window.title_bar.logo
    assert not logo.pixmap().isNull()
    assert logo.width() >= 48
    window.allow_quit = True
    window.close()


def test_main_editor_has_stable_aligned_geometry_without_nested_effects(qapp):
    window = MainWindow()
    window.show()
    window.resize(960, 700)
    qapp.processEvents()
    card = window.findChild(QFrame, 'translationCard')
    assert card.graphicsEffect() is None
    assert window.input.graphicsEffect() is None
    left = window.input.geometry().left()
    right = card.width() - window.input.geometry().right() - 1
    top = window.input.geometry().top()
    bottom = card.height() - window.input.geometry().bottom() - 1
    assert len({left, right, top, bottom}) == 1
    assert 24 <= left <= 25
    window.allow_quit = True
    window.close()


def test_main_window_replaces_the_system_title_bar(qapp):
    window = MainWindow()
    window.show()
    qapp.processEvents()

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.findChild(QPushButton, 'minimizeButton') is not None
    assert window.findChild(QPushButton, 'maximizeButton') is not None
    assert window.findChild(QPushButton, 'closeButton') is not None
    pin = window.findChild(QPushButton, 'pinButton')
    assert pin is not None
    pin.click()
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert pin.isChecked()
    pin.click()
    assert not window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    window.findChild(QPushButton, 'maximizeButton').click()
    qapp.processEvents()
    assert window.isMaximized()
    window.findChild(QPushButton, 'maximizeButton').click()
    qapp.processEvents()
    assert not window.isMaximized()

    window.allow_quit = True
    window.close()


def test_frameless_window_detects_resize_edges(qapp):
    window = MainWindow()
    window.resize(600, 400)
    assert window.resize_edges(QPoint(1, 1)) == (
        Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
    assert window.resize_edges(QPoint(599, 399)) == (
        Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
    assert window.resize_edges(QPoint(300, 200)) == Qt.Edge(0)
    window.allow_quit = True
    window.close()


def test_frameless_border_starts_native_resize(qapp, monkeypatch):
    class Handle:
        edges = Qt.Edge(0)

        def startSystemResize(self, edges):
            self.edges = edges
            return True

    window = MainWindow()
    window.resize(600, 400)
    window.show()
    qapp.processEvents()
    handle = Handle()
    monkeypatch.setattr(window, 'windowHandle', lambda: handle)
    QTest.mousePress(window.wallpaper, Qt.MouseButton.LeftButton, pos=QPoint(1, 200))
    assert handle.edges == Qt.Edge.LeftEdge
    window.allow_quit = True
    window.close()


def test_maximized_title_bar_still_starts_native_drag(qapp, monkeypatch):
    class Handle:
        started = False

        def startSystemResize(self, edges):
            return False

        def startSystemMove(self):
            self.started = True
            return True

    window = MainWindow()
    window.showMaximized()
    qapp.processEvents()
    handle = Handle()
    monkeypatch.setattr(window, 'windowHandle', lambda: handle)
    QTest.mousePress(window.title_bar, Qt.MouseButton.LeftButton, pos=QPoint(300, 22))
    assert handle.started
    window.allow_quit = True
    window.close()


def test_title_bar_double_click_and_tray_close_behavior(qapp):
    window = MainWindow()
    window.show()
    qapp.processEvents()
    QTest.mouseDClick(window.title_bar, Qt.MouseButton.LeftButton, pos=QPoint(300, 22))
    qapp.processEvents()
    assert window.isMaximized()
    window.showNormal()
    window.can_hide_to_tray = True
    window.show()
    window.findChild(QPushButton, 'closeButton').click()
    qapp.processEvents()
    assert not window.isVisible()
    window.allow_quit = True
    window.close()


def test_no_tray_keeps_the_frameless_canvas_and_close_quits(qapp, monkeypatch):
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.window = MainWindow()
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', lambda: False)
    desktop._tray()
    assert desktop.window.allow_quit
    assert desktop.window.findChildren(QMenuBar) == []
    desktop.window.close()


def test_wayland_screenshot_keeps_requesting_window_focused_and_restores_opacity(qapp, monkeypatch):
    from types import SimpleNamespace
    from paper_translator.app import DesktopApplication
    import paper_translator.app as app_module
    scheduled = []
    monkeypatch.setattr(app_module.QTimer, 'singleShot', lambda delay, callback: scheduled.append(callback))
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.settings = Settings()
    desktop.wayland = True
    desktop.capture_lock = False
    desktop.native_capture_id = None
    desktop.native_capture_timer = SimpleNamespace(stop=lambda: None)
    desktop.window = MainWindow()
    desktop.window.show()
    desktop.window.setWindowOpacity(.92)
    desktop.result_window = SimpleNamespace(hide=lambda: None, source=SimpleNamespace(clear=lambda: None))
    desktop.controller = SimpleNamespace(gate=SimpleNamespace(invalidate=lambda: None), pending=None)
    desktop.capture = SimpleNamespace(start=lambda: None)
    desktop.screenshot()
    assert scheduled
    assert not desktop.window.isMinimized()
    assert desktop.window.windowOpacity() == 0
    desktop._capture_cancel()
    assert desktop.window.windowOpacity() == pytest.approx(.92, abs=1 / 255)
    desktop.window.allow_quit = True
    desktop.window.close()


def test_native_gnome_screenshot_accepts_only_matching_capture(qapp, tmp_path):
    from types import SimpleNamespace
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.settings = Settings()
    desktop.wayland = True
    desktop.capture_lock = False
    desktop.capture_token = None
    desktop.native_capture_id = None
    desktop.native_capture_timer = SimpleNamespace(start=lambda _ms: None, stop=lambda: None)
    desktop.window = MainWindow()
    desktop.window.show()
    desktop.result_window = SimpleNamespace(hide=lambda: None, source=SimpleNamespace(clear=lambda: None))
    desktop.controller = SimpleNamespace(gate=SimpleNamespace(invalidate=lambda: None), pending=None,
                                        submit_image=lambda image: image.width())
    desktop.screenshot_native('capture-one')
    assert desktop.capture_lock
    desktop._native_cancel('stale')
    assert desktop.capture_lock
    path = tmp_path / 'capture.png'
    image = QImage(50, 20, QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    assert image.save(str(path))
    desktop._native_file('stale', str(path))
    assert desktop.capture_token is None
    desktop._native_file('capture-one', str(path))
    assert desktop.capture_token == 50
    assert desktop.native_capture_id is None
    desktop.window.allow_quit = True
    desktop.window.close()


def test_native_gnome_screenshot_uses_clipboard_image_if_file_is_unavailable(qapp):
    from types import SimpleNamespace
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.native_capture_id = 'capture-one'
    desktop.capture_lock = True
    desktop.settings = Settings()
    desktop.native_capture_timer = SimpleNamespace(stop=lambda: None)
    received = []
    desktop.controller = SimpleNamespace(submit_image=lambda image: received.append(image.size()) or 1)
    image = QImage(40, 30, QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    QApplication.clipboard().setImage(image)
    desktop._native_clipboard_changed()
    assert desktop.native_capture_id is None
    assert received == [image.size()]


def test_settings_dialog_previews_entire_window_opacity(qapp, tmp_path):
    wallpaper = tmp_path / 'wallpaper.webp'
    image = QImage(160, 90, QImage.Format.Format_RGB32)
    image.fill(QColor('#4f46e5'))
    assert image.save(str(wallpaper))
    dialog = SettingsDialog(Settings(wallpaper_path=str(wallpaper), window_opacity=38))
    assert dialog.wallpaper_path.text() == str(wallpaper)
    assert dialog.window_opacity.value() == 38
    assert not dialog.wallpaper_preview.pixmap.isNull()
    changes = []
    dialog.opacity_changed.connect(changes.append)
    dialog.window_opacity.setValue(72)
    assert dialog.windowOpacity() == pytest.approx(.72, abs=1 / 255)
    assert changes == [72]
    assert dialog.wallpaper_preview.opacity == 1.0
    result = dialog.values()
    assert result.wallpaper_path == str(wallpaper)
    assert result.window_opacity == 72
    dialog.close()


def test_dark_and_light_themes_animate_across_all_windows(qapp, spin):
    dialog = SettingsDialog(Settings(color_theme='dark'))
    changes = []
    dialog.theme_changed.connect(changes.append)
    assert dialog.color_theme.currentData() == 'dark'
    dialog.show()
    dialog.color_theme.setCurrentIndex(dialog.color_theme.findData('light'))
    assert changes == ['light']
    assert dialog.theme_name == 'light'
    assert dialog.wallpaper_preview.theme_name == 'light'
    assert dialog.theme_transition.state() == QAbstractAnimation.State.Running
    spin(lambda: dialog.theme_transition.state() == QAbstractAnimation.State.Stopped)
    assert THEMES['light']['accent'] in dialog.styleSheet()
    settings = dialog.values()
    assert settings.color_theme == 'light'

    main = MainWindow()
    main.refresh(settings)
    main.show()
    main.apply_theme('dark', animated=False)
    main.apply_theme('light', animated=True)
    assert main.theme_name == 'light'
    assert main.wallpaper.theme_name == 'light'
    assert main.theme_transition.state() == QAbstractAnimation.State.Running
    spin(lambda: main.theme_transition.state() == QAbstractAnimation.State.Stopped)
    result = ResultWindow()
    result.show()
    result.apply_theme('dark', animated=False)
    result.apply_theme(settings.color_theme, animated=True)
    assert result.theme_name == 'light'
    assert result.theme_transition.state() == QAbstractAnimation.State.Running
    spin(lambda: result.theme_transition.state() == QAbstractAnimation.State.Stopped)
    assert THEMES['light']['accent'] in result.styleSheet()

    assert int(THEMES['light']['card'].split(',')[-1][:-1]) < 170
    assert int(THEMES['light']['input'].split(',')[-1][:-1]) < 125
    assert int(THEMES['light']['input_focus'].split(',')[-1][:-1]) < 160
    assert '#4f46e5' not in dialog.styleSheet()

    dialog.close()
    main.allow_quit = True
    main.close()
    result.close()


def test_settings_action_buttons_have_text_only_and_muted_blue_theme(qapp):
    dialog = SettingsDialog(Settings(color_theme='light'))
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    for standard, label in ((QDialogButtonBox.StandardButton.Save, '保存'),
                            (QDialogButtonBox.StandardButton.Cancel, '取消')):
        button = buttons.button(standard)
        assert button.text() == label
        assert button.icon().isNull()
    assert THEMES['light']['accent'] in dialog.styleSheet()
    dialog.close()


def test_theme_transition_preserves_translucency_between_palettes():
    halfway = blend_palette(THEMES['dark'], THEMES['light'], .5)
    assert halfway['card'] == 'rgba(134,138,146,175)'
    assert halfway['input'].endswith(',51)')


def test_wallpaper_color_updates_buttons_and_result_window(qapp, tmp_path):
    wallpaper = tmp_path / 'red.png'
    image = QImage(80, 80, QImage.Format.Format_RGB32)
    image.fill(QColor('#ba5449'))
    assert image.save(str(wallpaper))
    extracted = QColor(theme_colors('light', str(wallpaper))['accent'])
    assert extracted.red() > extracted.blue() + 25
    main = MainWindow()
    result = ResultWindow()
    main.refresh(Settings(color_theme='light', wallpaper_path=str(wallpaper)))
    result.set_wallpaper(str(wallpaper))
    result.apply_theme('light', animated=False)
    assert extracted.name() in main.input.styleSheet()
    assert extracted.name() in result.styleSheet()
    assert result._result_colors['background'] != result_palette('light')['background']
    main.allow_quit = True
    main.close()
    result.close()


def test_wallpaper_preview_recolors_settings_buttons_and_can_reset(qapp, tmp_path):
    wallpaper = tmp_path / 'green.png'
    image = QImage(40, 40, QImage.Format.Format_RGB32)
    image.fill(QColor('#4a976e'))
    assert image.save(str(wallpaper))
    dialog = SettingsDialog(Settings(color_theme='light'))
    previews = []
    dialog.wallpaper_changed.connect(previews.append)
    dialog.wallpaper_path.setText(str(wallpaper))
    accent = theme_colors('light', str(wallpaper))['accent']
    assert accent in dialog.styleSheet()
    assert previews == [str(wallpaper)]
    dialog.wallpaper_path.clear()
    assert THEMES['light']['accent'] in dialog.styleSheet()
    dialog.close()


def test_cancelled_wallpaper_preview_restores_both_windows(qapp, tmp_path, monkeypatch):
    from paper_translator.app import DesktopApplication
    wallpaper = tmp_path / 'orange.png'
    image = QImage(24, 24, QImage.Format.Format_RGB32)
    image.fill(QColor('#c36b3d'))
    assert image.save(str(wallpaper))
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.settings = Settings(color_theme='light')
    desktop.window = MainWindow()
    desktop.result_window = ResultWindow()

    def preview_then_cancel(dialog):
        dialog.wallpaper_path.setText(str(wallpaper))
        assert desktop.window.wallpaper_path == str(wallpaper)
        assert desktop.result_window.wallpaper_path == str(wallpaper)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(SettingsDialog, 'exec', preview_then_cancel)
    desktop.show_settings()
    assert desktop.window.wallpaper_path == ''
    assert desktop.result_window.wallpaper_path == ''
    assert desktop.window._main_colors['accent'] == THEMES['light']['accent']
    desktop.window.allow_quit = True
    desktop.window.close()
    desktop.result_window.close()


def test_cancelled_theme_preview_restores_application_theme(qapp, monkeypatch):
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.settings = Settings(color_theme='dark')
    desktop.window = MainWindow()
    desktop.result_window = ResultWindow()

    def preview_then_cancel(dialog):
        dialog.color_theme.setCurrentIndex(dialog.color_theme.findData('light'))
        assert desktop.window.theme_name == 'light'
        assert desktop.result_window.theme_name == 'light'
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(SettingsDialog, 'exec', preview_then_cancel)
    desktop.show_settings()
    assert desktop.window.theme_name == 'dark'
    assert desktop.result_window.theme_name == 'dark'
    desktop.window.allow_quit = True
    desktop.window.close()
    desktop.result_window.close()


def test_cancelled_opacity_preview_restores_all_application_windows(qapp, monkeypatch):
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.settings = Settings(window_opacity=84)
    desktop.window = MainWindow()
    desktop.result_window = ResultWindow()
    desktop._apply_opacity(84)

    def preview_then_cancel(dialog):
        dialog.window_opacity.setValue(46)
        assert desktop.window.windowOpacity() == pytest.approx(.46, abs=1 / 255)
        assert desktop.result_window.windowOpacity() == pytest.approx(.46, abs=1 / 255)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(SettingsDialog, 'exec', preview_then_cancel)
    desktop.show_settings()
    assert desktop.window.windowOpacity() == pytest.approx(.84, abs=1 / 255)
    assert desktop.result_window.windowOpacity() == pytest.approx(.84, abs=1 / 255)
    desktop.window.allow_quit = True
    desktop.window.close()
    desktop.result_window.close()


def test_theme_combo_popup_has_no_native_white_container(qapp):
    dialog = SettingsDialog(Settings(color_theme='dark'))
    dialog.show()
    dialog.color_theme.showPopup()
    qapp.processEvents()
    popup = dialog.color_theme.view().window()
    assert popup.property('paperTranslatorTheme') == 'dark'
    assert popup.palette().window().color().name() == '#111827'
    dialog.color_theme.hidePopup()
    dialog.close()


def test_api_settings_are_visually_separated_without_hint_copy(qapp):
    dialog = SettingsDialog(Settings())
    groups = {group.title() for group in dialog.findChildren(QGroupBox)}
    assert {'百度翻译', 'AI 论文精校'} <= groups
    labels = ' '.join(label.text() for label in dialog.findChildren(QLabel))
    assert '两类 API 都由你自行配置和付费' not in labels
    assert '密钥优先存入系统密钥库' not in labels
    dialog.close()


def test_result_window_preserves_source_and_displays_review_warning(qapp):
    window = ResultWindow()
    window.display(TranslationResult('attention', '初译', mode='paper', warning='复核失败'))
    assert window.source.toPlainText() == 'attention'
    assert '初译' in window.output.toPlainText()
    assert '复核失败' in window.output.toPlainText()
    window.close()


def test_result_stays_visible_until_closed_and_updates_on_next_translation(qapp):
    window = ResultWindow()
    presented = []
    window.presented.connect(lambda: presented.append(True))
    window.display(TranslationResult('first', '第一句'))
    assert window.isVisible()
    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    window.prepare('second')
    assert window.isVisible()
    assert window.output.toPlainText() == '第一句'
    window.display(TranslationResult('second', '第二句'))
    assert window.isVisible()
    assert window.output.toPlainText() == '第二句'
    assert len(presented) == 2
    window.close()
    assert not window.isVisible()
    window.display(TranslationResult('third', '第三句'))
    assert window.isVisible()
    window.close()


def test_result_hover_highlights_corresponding_sentences_in_both_texts(qapp):
    window = ResultWindow()
    window.display(TranslationResult('First sentence. Second sentence.', '第一句。第二句。',
                                     sentence_pairs=[(0, 15, 0, 4), (16, 32, 4, 8)]))
    try:
        cursor = window.source.textCursor()
        cursor.setPosition(window.source.toPlainText().index('Second'))
        QTest.mouseMove(window.source.viewport(), window.source.cursorRect(cursor).center())
        qapp.processEvents()
        source_ranges = [(item.cursor.selectionStart(), item.cursor.selectionEnd())
                         for item in window.source.extraSelections()]
        output_ranges = [(item.cursor.selectionStart(), item.cursor.selectionEnd())
                         for item in window.output.extraSelections()]
        assert source_ranges == [(16, 32)]
        assert output_ranges == [(4, 8)]
        window.prepare('New text')
        assert window.isVisible()
        assert window.source.toPlainText() == 'First sentence. Second sentence.'
        assert [(item.cursor.selectionStart(), item.cursor.selectionEnd())
                for item in window.source.extraSelections()] == [(16, 32)]
        window.display(TranslationResult('New text', '新译文'))
        assert window.source.toPlainText() == 'New text'
        assert not window.source.extraSelections()
        assert not window.output.extraSelections()
    finally:
        window.close()


def test_result_hover_from_translation_ignores_warning_and_maps_by_order(qapp):
    window = ResultWindow()
    window.display(TranslationResult('A. B.', '甲。乙。', warning='注意。',
                                     sentence_pairs=[(0, 2, 0, 2), (3, 5, 2, 4)]))
    try:
        cursor = window.output.textCursor()
        cursor.setPosition(window.output.toPlainText().index('乙'))
        QTest.mouseMove(window.output.viewport(), window.output.cursorRect(cursor).center())
        qapp.processEvents()
        source_selection = window.source.extraSelections()
        output_selection = window.output.extraSelections()
        assert source_selection[0].cursor.selectedText().strip() == 'B.'
        assert output_selection[0].cursor.selectedText().strip() == '乙。'
        previous = output_selection[0].cursor.selectionStart()
        warning_cursor = window.output.textCursor()
        warning_cursor.setPosition(window.output.toPlainText().index('注意'))
        QTest.mouseMove(window.output.viewport(), window.output.cursorRect(warning_cursor).center())
        qapp.processEvents()
        assert window.output.extraSelections()[0].cursor.selectionStart() == previous
    finally:
        window.close()


def test_result_hover_uses_translation_pairs_for_one_to_many_sentences(qapp):
    window = ResultWindow()
    result = TranslationResult('First sentence. Second sentence.', '第一句。另一种说法。\n第二句。',
                               sentence_pairs=[(0, 15, 0, 10), (16, 32, 11, 15)])
    window.display(result)
    try:
        cursor = window.output.textCursor()
        cursor.setPosition(window.output.toPlainText().index('另一种'))
        QTest.mouseMove(window.output.viewport(), window.output.cursorRect(cursor).center())
        qapp.processEvents()
        source = window.source.extraSelections()
        output = window.output.extraSelections()
        assert source[0].cursor.selectedText() == 'First sentence.'
        assert output[0].cursor.selectedText() == '第一句。另一种说法。'
    finally:
        window.close()


def test_result_hover_does_not_guess_pairs_when_counts_differ(qapp):
    window = ResultWindow()
    window.display(TranslationResult('First. Second.', '第一句。另一句。第二句。'))
    try:
        cursor = window.source.textCursor()
        cursor.setPosition(window.source.toPlainText().index('Second'))
        QTest.mouseMove(window.source.viewport(), window.source.cursorRect(cursor).center())
        qapp.processEvents()
        assert window.source.extraSelections()
        assert not window.output.extraSelections()
    finally:
        window.close()


def test_result_hover_scrolls_only_matched_other_text_into_view(qapp):
    source_parts = [f'Sentence {index}.' for index in range(24)]
    output_parts = [f'译文第{index}句。' for index in range(24)]
    source = '\n'.join(source_parts)
    output = '\n'.join(output_parts)
    pairs = []
    source_offset = output_offset = 0
    for source_part, output_part in zip(source_parts, output_parts):
        pairs.append((source_offset, source_offset + len(source_part),
                      output_offset, output_offset + len(output_part)))
        source_offset += len(source_part) + 1
        output_offset += len(output_part) + 1
    window = ResultWindow()
    window.display(TranslationResult(source, output, sentence_pairs=pairs))
    try:
        window.source.verticalScrollBar().setValue(window.source.verticalScrollBar().maximum())
        window.output.verticalScrollBar().setValue(0)
        qapp.processEvents()
        cursor = window.source.textCursor()
        cursor.setPosition(pairs[-1][0])
        QTest.mouseMove(window.source.viewport(), window.source.cursorRect(cursor).center())
        qapp.processEvents()
        assert window.output.verticalScrollBar().value() > 0
        counterpart = window.output.textCursor()
        counterpart.setPosition(pairs[-1][2])
        rect = window.output.cursorRect(counterpart)
        assert 0 <= rect.center().y() < window.output.viewport().height()
        assert window.source.verticalScrollBar().value() == window.source.verticalScrollBar().maximum()
        window.source.verticalScrollBar().setValue(0)
        window.output.verticalScrollBar().setValue(window.output.verticalScrollBar().maximum())
        qapp.processEvents()
        translated_cursor = window.output.textCursor()
        translated_cursor.setPosition(pairs[-1][2])
        QTest.mouseMove(window.output.viewport(), window.output.cursorRect(translated_cursor).center())
        qapp.processEvents()
        assert window.source.verticalScrollBar().value() > 0
    finally:
        window.close()


def test_result_text_boxes_can_be_resized_by_dragging_divider(qapp):
    window = ResultWindow()
    window.display(TranslationResult('Original.', '译文。'))
    try:
        assert isinstance(window.text_splitter, QSplitter)
        before = window.text_splitter.sizes()
        handle = window.text_splitter.handle(1)
        center = handle.rect().center()
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(handle, center + QPoint(0, 45))
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=center + QPoint(0, 45))
        qapp.processEvents()
        after = window.text_splitter.sizes()
        assert after[0] > before[0]
        assert after[1] < before[1]
    finally:
        window.close()


def test_region_overlay_crops_and_cancel_emits_no_image(qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QPixmap
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(QColor('white'))
    overlay = RegionOverlay(QPixmap.fromImage(img), QRect(0, 0, 100, 100))
    cropped = overlay.crop(QRect(10, 20, 30, 40))
    assert (cropped.width(), cropped.height()) == (30, 40)
    images, cancelled = [], []
    overlay.captured.connect(images.append)
    overlay.cancelled.connect(lambda: cancelled.append(True))
    overlay.cancel()
    assert not images and cancelled == [True]


def test_portal_cancel_does_not_emit_stale_uri(qapp):
    capture = PortalCapture()
    images, cancellations = [], []
    capture.path_ready.connect(images.append)
    capture.cancelled.connect(lambda: cancellations.append(True))
    capture.waiting = True
    capture.response(1, {})
    capture.response(0, {'uri': 'file:///tmp/stale.png'})
    assert not images
    assert cancellations == [True]


def test_main_window_can_close_when_program_is_quitting(qapp):
    window = MainWindow()
    window.show()
    window.allow_quit = True
    assert window.close() is True


def test_old_portal_method_error_cannot_cancel_new_capture(qapp):
    class Watcher:
        def deleteLater(self):
            pass
    capture = PortalCapture()
    capture.waiting = True
    capture.watcher = Watcher()
    errors = []
    capture.error.connect(errors.append)
    capture._called(Watcher())
    assert capture.waiting is True
    assert not errors


def test_current_portal_error_is_reported_with_supported_qt_api(qapp):
    from PySide6.QtDBus import QDBusMessage
    class Watcher:
        def reply(self):
            return QDBusMessage.createError('org.test.Failed', 'failed')
        def deleteLater(self):
            pass
    capture = PortalCapture()
    capture.waiting = True
    capture.watcher = Watcher()
    errors = []
    capture.error.connect(errors.append)
    capture._called(capture.watcher)
    assert not capture.waiting
    assert len(errors) == 1


def test_old_portal_response_is_ignored_after_new_request(qapp):
    from PySide6.QtDBus import QDBusMessage
    capture = PortalCapture()
    capture.waiting = True
    capture.request_path = '/new/request'
    paths = []
    capture.path_ready.connect(paths.append)
    message = QDBusMessage.createSignal('/old/request', 'org.freedesktop.portal.Request', 'Response')
    capture.response(0, {'uri': 'file:///tmp/old.png'}, message)
    assert capture.waiting is True
    assert not paths


def test_ipc_external_clients_do_not_emit_wrapper_warnings(qapp, spin, tmp_path):
    import os
    import socket as native_socket
    from PySide6.QtCore import QCoreApplication, QEvent, qInstallMessageHandler
    if os.name == 'nt':
        pytest.skip('Unix socket integration is Linux-specific')
    messages, received = [], []
    server = LocalCommandServer(str(tmp_path / 'external.sock'))
    server.command.connect(received.append)
    server.start()
    old = qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    try:
        for _ in range(12):
            with native_socket.socket(native_socket.AF_UNIX) as client:
                client.connect(server.name)
                client.sendall(b'{"command":"bridge","status":"ok"}\n')
        spin(lambda: len(received) == 12 and not server.clients)
        assert not messages, messages
        # A client which sends no newline must still expire, without a wrapper warning.
        with native_socket.socket(native_socket.AF_UNIX) as client:
            client.connect(server.name)
            spin(lambda: bool(server.clients))
            spin(lambda: not server.clients, timeout=4)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not server.timers
        assert not messages, messages
    finally:
        server.close()
        qInstallMessageHandler(old)


def test_settings_auto_direction_preserves_hidden_language_values():
    dialog = SettingsDialog(Settings(source_language='en', target_language='zh'))
    assert dialog.auto_direction.isChecked()
    assert 'source_language' not in dialog.inputs
    assert 'target_language' not in dialog.inputs
    dialog.auto_direction.setChecked(False)
    settings = dialog.values()
    assert not settings.auto_direction
    assert settings.source_language == 'en'
    assert settings.target_language == 'zh'
    dialog.close()


def test_paper_result_only_shows_final_translation_and_ambiguity(qapp):
    window = ResultWindow()
    window.display(TranslationResult('attention', '最终译文', mode='paper', reviewed=True,
        draft='初译', terms=[{'source':'x','target':'y','note':'解释'}], notes='解释', ambiguities=['含义待确认']))
    assert window.output.toPlainText() == '最终译文\n\n歧义 / 需核对\n含义待确认'
    window.close()


def test_retry_context_belongs_to_visible_source_not_pending_selection(spin):
    class ContextTranslator:
        def __init__(self):
            self.release = threading.Event()
            self.calls = []
        def translate(self, text, settings, cancelled=lambda: False, context=''):
            self.calls.append((text, context))
            if text == 'visible':
                self.release.wait(3)
            return TranslationResult(text, 'translation', context=context)
    translator = ContextTranslator()
    controller = TranslationController(Settings(), translator=translator)
    visible = []
    controller.source_ready.connect(visible.append)
    controller.submit_text('visible', context='visible context')
    try:
        spin(lambda: visible == ['visible'])
        controller.submit_text('pending', context='pending context')
        assert controller.last_context == 'visible context'
        controller.submit_text('edited visible', context=controller.last_context)
    finally:
        translator.release.set()
        spin(lambda: not controller.busy)
    assert translator.calls[-1] == ('edited visible', 'visible context')
