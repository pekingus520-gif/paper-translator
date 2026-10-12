from dataclasses import replace

from PySide6.QtCore import (QEvent, QEasingCurve, QPoint, Property, QPropertyAnimation,
                           Qt, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QCursor, QKeySequence, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QSlider, QSpinBox, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget)


THEMES = {
    'dark': {
        'canvas': '#090e1b', 'overlay': (7, 11, 23, 76), 'text': '#f8fafc',
        'muted': '#94a3b8', 'card': 'rgba(12,20,38,218)',
        'card_border': 'rgba(148,163,184,52)', 'input': 'rgba(255,255,255,14)',
        'input_focus': 'rgba(255,255,255,22)', 'input_border': 'rgba(148,163,184,56)',
        'accent': '#818cf8', 'accent_hover': '#a5b4fc', 'button_text': '#111827',
        'preview_border': (148, 163, 184, 52),
    },
    'light': {
        'canvas': '#edf2fb', 'overlay': (245, 248, 255, 72), 'text': '#172033',
        'muted': '#64748b', 'card': 'rgba(255,255,255,222)',
        'card_border': 'rgba(100,116,139,60)', 'input': 'rgba(248,250,252,218)',
        'input_focus': 'rgba(255,255,255,238)', 'input_border': 'rgba(100,116,139,70)',
        'accent': '#4f46e5', 'accent_hover': '#4338ca', 'button_text': '#ffffff',
        'preview_border': (100, 116, 139, 70),
    },
}


def theme_colors(name):
    return THEMES.get(name, THEMES['dark'])


def _qcolor(value):
    if isinstance(value, tuple):
        return QColor(*value)
    if isinstance(value, QColor):
        return QColor(value)
    return QColor(value)


def _color_css(color):
    return f'rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})'


def blend_palette(start, end, progress):
    progress = max(0.0, min(1.0, float(progress)))
    if progress >= 1.0:
        return dict(end)
    blended = {}
    for key, target in end.items():
        source = _qcolor(start.get(key, target))
        destination = _qcolor(target)
        channels = [round(a + (b - a) * progress) for a, b in zip(
            source.getRgb(), destination.getRgb())]
        blended[key] = _color_css(QColor(*channels))
    return blended


def dialog_palette(name):
    base = theme_colors(name)
    if name == 'light':
        values = {
            'background': '#f3f6fc', 'text': '#172033', 'label': '#475569',
            'muted': '#64748b', 'panel': '#ffffff', 'border': '#cbd5e1',
            'selected': '#e3e8f2', 'group': 'rgba(255,255,255,205)',
            'title_background': '#f3f6fc', 'groove': '#cbd5e1', 'handle': '#4f46e5',
        }
    else:
        values = {
            'background': '#0f172a', 'text': '#f8fafc', 'label': '#cbd5e1',
            'muted': '#94a3b8', 'panel': '#111827', 'border': '#334155',
            'selected': '#1e293b', 'group': 'rgba(17,24,39,120)',
            'title_background': '#0f172a', 'groove': '#334155', 'handle': '#e0e7ff',
        }
    values.update({key: base[key] for key in ('accent', 'accent_hover', 'button_text')})
    return values


def result_palette(name):
    base = theme_colors(name)
    if name == 'light':
        values = {'background': '#f3f6fc', 'panel': '#ffffff', 'text': '#172033',
                  'muted': '#64748b', 'border': '#cbd5e1'}
    else:
        values = {'background': '#0f172a', 'panel': '#111827', 'text': '#f8fafc',
                  'muted': '#94a3b8', 'border': '#334155'}
    values.update({key: base[key] for key in ('accent', 'accent_hover', 'button_text')})
    return values


class SubmitTextEdit(QTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event):
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier and
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ThemedComboBox(QComboBox):
    """Themes both the view and Qt's private popup frame."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_name = 'dark'

    def apply_popup_theme(self, name):
        self.theme_name = name if name in THEMES else 'dark'
        if self.theme_name == 'light':
            panel, text, border, selected = '#ffffff', '#172033', '#cbd5e1', '#4f46e5'
        else:
            panel, text, border, selected = '#111827', '#f8fafc', '#334155', '#818cf8'
        popup = self.view().window()
        popup.setProperty('paperTranslatorTheme', self.theme_name)
        palette = popup.palette()
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base,
                     QPalette.ColorRole.Button):
            palette.setColor(role, QColor(panel))
        palette.setColor(QPalette.ColorRole.Text, QColor(text))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(text))
        popup.setPalette(palette)
        popup.setAutoFillBackground(True)
        popup.setStyleSheet(f'''QFrame {{ background:{panel}; border:1px solid {border};
            padding:0; margin:0; }}
            QAbstractItemView {{ color:{text}; background:{panel}; border:0; outline:0;
                padding:0; margin:0; selection-background-color:{selected}; }}
            QAbstractItemView::item {{ min-height:30px; padding:4px 10px; border:0; }}''')

    def showPopup(self):
        self.apply_popup_theme(self.theme_name)
        super().showPopup()
        self.apply_popup_theme(self.theme_name)


class WallpaperCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.theme_name = 'dark'
        self._theme_colors = dict(THEMES['dark'])
        self._wallpaper_opacity = 0.0
        self.target_opacity = 1.0
        self.fade = QPropertyAnimation(self, b'wallpaperOpacity', self)
        self.fade.setDuration(320)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def wallpaperOpacity(self):
        return self._wallpaper_opacity

    def setWallpaperOpacity(self, value):
        self._wallpaper_opacity = max(0.0, min(1.0, float(value)))
        self.update()

    wallpaperOpacity = Property(float, wallpaperOpacity, setWallpaperOpacity)

    def set_appearance(self, path):
        self.pixmap = QPixmap(path) if path else QPixmap()
        self.target_opacity = 1.0
        self.fade.stop()
        self.fade.setStartValue(0.0 if not self.pixmap.isNull() else self.target_opacity)
        self.fade.setEndValue(self.target_opacity)
        self.fade.start()
        self.update()

    def set_theme(self, name):
        self.theme_name = name if name in THEMES else 'dark'
        self._theme_colors = dict(theme_colors(self.theme_name))
        self.update()

    def set_theme_colors(self, colors, name=None):
        if name in THEMES:
            self.theme_name = name
        self._theme_colors = dict(colors)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        colors = self._theme_colors
        painter.fillRect(self.rect(), QColor(colors['canvas']))
        if not self.pixmap.isNull():
            scaled = self.pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                        Qt.TransformationMode.SmoothTransformation)
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            painter.setOpacity(self._wallpaper_opacity)
            painter.drawPixmap(self.rect(), scaled, scaled.rect().adjusted(x, y, -x, -y))
        painter.setOpacity(1.0)
        painter.fillRect(self.rect(), _qcolor(colors['overlay']))


class HoverButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._level = 0.0
        self.theme_name = 'dark'
        self.motion = QPropertyAnimation(self, b'hoverLevel', self)
        self.motion.setDuration(150)
        self.motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restyle()

    def hoverLevel(self):
        return self._level

    def setHoverLevel(self, value):
        self._level = float(value)
        self._restyle()

    hoverLevel = Property(float, hoverLevel, setHoverLevel)

    def _animate(self, target):
        self.motion.stop()
        self.motion.setStartValue(self._level)
        self.motion.setEndValue(target)
        self.motion.start()

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def _restyle(self):
        if self.theme_name == 'light':
            color = '#172033'
            background = f'rgba(255,255,255,{round(150 + self._level * 70)})'
            border_color = f'rgba(71,85,105,{round(45 + self._level * 60)})'
        else:
            color = '#f8fafc'
            background = f'rgba(255,255,255,{round(30 + self._level * 25)})'
            border_color = f'rgba(255,255,255,{round(55 + self._level * 65)})'
        self.setStyleSheet(f'''QPushButton {{ color:{color}; background:{background};
            border:1px solid {border_color}; border-radius:12px;
            padding:8px 18px; font-weight:600; }}''')

    def apply_theme(self, name):
        self.theme_name = name if name in THEMES else 'dark'
        colors = theme_colors(self.theme_name)
        self._restyle()


class WindowControlButton(QPushButton):
    def __init__(self, text, name, close_button=False, parent=None):
        super().__init__(text, parent)
        self.close_button = close_button
        self.theme_name = 'dark'
        self.setObjectName(name)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_theme('dark')

    def apply_theme(self, name):
        self.theme_name = name if name in THEMES else 'dark'
        colors = theme_colors(self.theme_name)
        if self.theme_name == 'light':
            color, background = '#334155', 'rgba(255,255,255,145)'
            border, pressed = 'rgba(71,85,105,38)', 'rgba(226,232,240,220)'
            hover = 'rgba(239,68,68,220)' if self.close_button else 'rgba(255,255,255,225)'
        else:
            color, background = '#f8fafc', 'rgba(255,255,255,12)'
            border, pressed = 'rgba(255,255,255,25)', 'rgba(255,255,255,55)'
            hover = 'rgba(239,68,68,220)' if self.close_button else 'rgba(255,255,255,38)'
        accent_border = ('rgba(79,70,229,90)' if self.theme_name == 'light'
                         else 'rgba(129,140,248,100)')
        self.setStyleSheet(f'''QPushButton {{ color:{color}; background:{background};
            border:1px solid {border}; border-radius:11px; font-size:17px;
            font-weight:500; padding:0; }}
            QPushButton:hover {{ color:{'#ffffff' if self.close_button else color};
                background:{hover}; border-color:{accent_border}; }}
            QPushButton:pressed {{ background:{pressed}; }}''')


class WindowTitleBar(QFrame):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._fallback_drag_offset = None
        self._fallback_drag_ratio = 0.5
        self._fallback_drag_y = 0
        self.setObjectName('windowTitleBar')
        self.setFixedHeight(44)
        self.setStyleSheet('QFrame#windowTitleBar { background:transparent; border:0; }')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.brand_mark = QLabel('●')
        self.brand_mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.brand_mark.setStyleSheet('color:#818cf8; font-size:12px;')
        layout.addWidget(self.brand_mark)
        self.brand = QLabel('Paper Translator')
        self.brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.brand.setStyleSheet(
            'color:#f8fafc; font-size:22px; font-weight:700; letter-spacing:0.4px;')
        layout.addWidget(self.brand)
        layout.addStretch()
        self.settings_button = HoverButton('设置')
        layout.addWidget(self.settings_button)
        self.minimize_button = WindowControlButton('−', 'minimizeButton')
        self.maximize_button = WindowControlButton('□', 'maximizeButton')
        self.close_button = WindowControlButton('×', 'closeButton', close_button=True)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(window.toggle_maximize)
        self.close_button.clicked.connect(window.close)

    def apply_theme(self, name):
        colors = theme_colors(name)
        self.brand.setStyleSheet(
            f"color:{colors['text']}; font-size:22px; font-weight:700; letter-spacing:0.4px;")
        self.brand_mark.setStyleSheet(f"color:{colors['accent']}; font-size:12px;")
        self.settings_button.apply_theme(name)
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            button.apply_theme(name)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        point = self.mapTo(self.window, event.position().toPoint())
        edges = self.window.resize_edges(point)
        handle = self.window.windowHandle()
        if edges and handle and handle.startSystemResize(edges):
            event.accept()
            return
        if handle and handle.startSystemMove():
            event.accept()
            return
        self._fallback_drag_ratio = event.position().x() / max(1, self.width())
        self._fallback_drag_y = event.position().y()
        self._fallback_drag_offset = (
            event.globalPosition().toPoint() - self.window.frameGeometry().topLeft())
        event.accept()

    def mouseMoveEvent(self, event):
        if (self._fallback_drag_offset is not None and
                event.buttons() & Qt.MouseButton.LeftButton):
            if self.window.isMaximized():
                self.window.showNormal()
                self._fallback_drag_offset = QPoint(
                    round(self.window.width() * self._fallback_drag_ratio),
                    min(round(self._fallback_drag_y), self.height()))
            self.window.move(event.globalPosition().toPoint() - self._fallback_drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._fallback_drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class WallpaperPreview(QFrame):
    def __init__(self, path='', parent=None):
        super().__init__(parent)
        self.setObjectName('wallpaperPreview')
        self.setMinimumHeight(210)
        self.pixmap = QPixmap(path) if path else QPixmap()
        self.opacity = 1.0
        self.theme_name = 'dark'

    def set_image(self, path):
        self.pixmap = QPixmap(path) if path else QPixmap()
        self.update()

    def set_theme(self, name):
        self.theme_name = name if name in THEMES else 'dark'
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = theme_colors(self.theme_name)
        painter.fillRect(self.rect(), QColor(colors['canvas']))
        if self.pixmap.isNull():
            painter.setPen(QColor(colors['muted']))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '未选择壁纸')
        else:
            scaled = self.pixmap.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            x = max(0, (scaled.width() - self.width()) // 2)
            y = max(0, (scaled.height() - self.height()) // 2)
            painter.setOpacity(self.opacity)
            painter.drawPixmap(self.rect(), scaled, scaled.rect().adjusted(x, y, -x, -y))
            painter.setOpacity(1.0)
            painter.fillRect(self.rect(), _qcolor(colors['overlay']))
        painter.setPen(_qcolor(colors['preview_border']))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 14, 14)


class SettingsDialog(QDialog):
    theme_changed = Signal(str)
    opacity_changed = Signal(int)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.initial = replace(settings)
        self.setWindowTitle('翻译设置')
        self.resize(620, 570)
        self.theme_name = settings.color_theme if settings.color_theme in THEMES else 'dark'
        self._dialog_colors = dialog_palette(self.theme_name)
        self._theme_start = self._dialog_colors
        self._theme_target = self._dialog_colors
        self.theme_transition = QVariantAnimation(self)
        self.theme_transition.setDuration(300)
        self.theme_transition.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.theme_transition.valueChanged.connect(self._theme_frame)
        self.theme_transition.finished.connect(
            lambda: self._render_dialog_theme(self._theme_target))
        self._render_dialog_theme(self._dialog_colors)
        self.inputs = {}
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.tabs = tabs
        layout.addWidget(tabs)

        general = QWidget()
        form = QFormLayout(general)
        self.mode = ThemedComboBox()
        self.mode.addItem('日常：百度翻译', 'daily')
        self.mode.addItem('论文：术语与语义精校', 'paper')
        self.mode.setCurrentIndex(1 if settings.mode == 'paper' else 0)
        form.addRow('模式', self.mode)
        self.selection = QCheckBox('拖选文字后自动翻译')
        self.selection.setChecked(settings.selection_enabled)
        form.addRow('实时划词', self.selection)
        self.auto_direction = QCheckBox('检测中文译成英文，检测英文译成中文')
        self.auto_direction.setChecked(settings.auto_direction)
        form.addRow('中英自动互译', self.auto_direction)
        for name, label in [('screenshot_hotkey', '截图快捷键'),
                            ('toggle_hotkey', '总开关快捷键')]:
            self._line(form, name, label, settings)
        tabs.addTab(general, '基本')

        appearance = QWidget()
        form = QFormLayout(appearance)
        form.setVerticalSpacing(14)
        self.color_theme = ThemedComboBox()
        self.color_theme.addItem('深色', 'dark')
        self.color_theme.addItem('浅色', 'light')
        self.color_theme.setCurrentIndex(max(0, self.color_theme.findData(settings.color_theme)))
        form.addRow('颜色主题', self.color_theme)
        self.wallpaper_preview = WallpaperPreview(settings.wallpaper_path)
        self.wallpaper_preview.set_theme(settings.color_theme)
        form.addRow(self.wallpaper_preview)
        self.wallpaper_path = QLineEdit(settings.wallpaper_path)
        self.wallpaper_path.setReadOnly(True)
        browse = QPushButton('选择图片')
        clear = QPushButton('清除')
        browse.clicked.connect(self._choose_wallpaper)
        clear.clicked.connect(self.wallpaper_path.clear)
        self.wallpaper_path.textChanged.connect(self.wallpaper_preview.set_image)
        wallpaper_row = QWidget()
        wallpaper_layout = QHBoxLayout(wallpaper_row)
        wallpaper_layout.setContentsMargins(0, 0, 0, 0)
        wallpaper_layout.addWidget(self.wallpaper_path, 1)
        wallpaper_layout.addWidget(browse)
        wallpaper_layout.addWidget(clear)
        form.addRow('窗口壁纸', wallpaper_row)
        self.window_opacity = QSlider(Qt.Orientation.Horizontal)
        self.window_opacity.setRange(30, 100)
        self.window_opacity.setValue(settings.window_opacity)
        self.opacity_value = QLabel(f'{settings.window_opacity}%')
        def preview_opacity(value):
            self.opacity_value.setText(f'{value}%')
            self.setWindowOpacity(value / 100)
            self.opacity_changed.emit(value)
        self.window_opacity.valueChanged.connect(preview_opacity)
        self.color_theme.currentIndexChanged.connect(self._theme_selected)
        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(self.window_opacity, 1)
        opacity_layout.addWidget(self.opacity_value)
        form.addRow('窗口透明度', opacity_row)
        tabs.addTab(appearance, '外观')

        api = QWidget()
        api_layout = QVBoxLayout(api)
        api_layout.setContentsMargins(0, 0, 0, 0)
        api_layout.setSpacing(14)
        baidu_group = QGroupBox('百度翻译')
        baidu_group.setObjectName('baiduApiGroup')
        baidu_form = QFormLayout(baidu_group)
        for name, label in [('baidu_app_id', 'App ID'), ('baidu_key', '密钥'),
                            ('baidu_url', '接口地址')]:
            self._line(baidu_form, name, label, settings, secret=name.endswith('_key'))
        api_layout.addWidget(baidu_group)
        ai_group = QGroupBox('AI 论文精校')
        ai_group.setObjectName('aiApiGroup')
        ai_form = QFormLayout(ai_group)
        for name, label in [('ai_url', '接口地址'), ('ai_key', '密钥'),
                            ('ai_model', '模型名称')]:
            self._line(ai_form, name, label, settings, secret=name.endswith('_key'))
        api_layout.addWidget(ai_group)
        api_layout.addStretch()
        tabs.addTab(api, 'API')

        ocr = QWidget()
        form = QFormLayout(ocr)
        for name, label in [('tesseract_path', 'Tesseract 可执行文件'), ('ocr_languages', 'OCR 语言包')]:
            self._line(form, name, label, settings)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setValue(settings.timeout_seconds)
        form.addRow('API 超时（秒）', self.timeout)
        self.limit = QSpinBox()
        self.limit.setRange(1, 10000)
        self.limit.setValue(settings.max_text_chars)
        form.addRow('单次字符上限', self.limit)
        note = QLabel('OCR 在本地运行；路径留空时自动查找 Tesseract。\n默认 eng；中英混合可填 eng+chi_sim，须先安装对应语言包。')
        note.setWordWrap(True)
        form.addRow(note)
        tabs.addTab(ocr, 'OCR 与请求')
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setWindowOpacity(settings.window_opacity / 100)
        self.apply_theme(self.theme_name, animated=False)

    def _render_dialog_theme(self, colors):
        self._dialog_colors = dict(colors)
        self.setStyleSheet(f'''
            QDialog {{ background:{colors['background']}; color:{colors['text']}; }}
            QLabel, QCheckBox {{ color:{colors['label']}; font-size:14px; }}
            QTabWidget::pane {{ border:0; margin-top:8px; }}
            QTabBar::tab {{ color:{colors['muted']}; background:transparent; padding:10px 16px;
                border-radius:9px; margin-right:4px; }}
            QTabBar::tab:selected {{ color:{colors['text']}; background:{colors['selected']}; font-weight:600; }}
            QLineEdit, QComboBox, QSpinBox {{ color:{colors['text']}; background:{colors['panel']};
                border:1px solid {colors['border']}; border-radius:9px; padding:7px 9px; min-height:20px; }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color:{colors['accent']}; }}
            QComboBox::drop-down {{ border:0; width:28px; background:transparent; }}
            QComboBox::down-arrow {{ image:none; width:0; height:0; }}
            QGroupBox {{ color:{colors['text']}; font-size:15px; font-weight:700;
                border:1px solid {colors['border']}; border-radius:14px; margin-top:14px;
                padding:16px 12px 12px 12px; background:{colors['group']}; }}
            QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:0 7px;
                background:{colors['title_background']}; }}
            QPushButton {{ color:{colors['button_text']}; background:{colors['accent']}; border:0; border-radius:9px;
                padding:8px 15px; font-weight:600; }}
            QPushButton:hover {{ background:{colors['accent_hover']}; }}
            QSlider::groove:horizontal {{ height:5px; background:{colors['groove']}; border-radius:2px; }}
            QSlider::sub-page:horizontal {{ background:{colors['accent']}; border-radius:2px; }}
            QSlider::handle:horizontal {{ width:16px; margin:-6px 0; border-radius:8px;
                background:{colors['handle']}; }}
        ''')

    def _theme_frame(self, progress):
        self._render_dialog_theme(blend_palette(
            self._theme_start, self._theme_target, progress))

    def apply_theme(self, name, animated=True):
        name = name if name in THEMES else 'dark'
        target = dialog_palette(name)
        should_animate = animated and self.isVisible() and name != self.theme_name
        self.theme_name = name
        if hasattr(self, 'mode'):
            self.mode.apply_popup_theme(name)
            self.color_theme.apply_popup_theme(name)
        self.theme_transition.stop()
        if should_animate:
            self._theme_start = dict(self._dialog_colors)
            self._theme_target = target
            self.theme_transition.setStartValue(0.0)
            self.theme_transition.setEndValue(1.0)
            self.theme_transition.start()
        else:
            self._theme_target = target
            self._render_dialog_theme(target)

    def _theme_selected(self, _index=None):
        name = self.color_theme.currentData()
        self.apply_theme(name)
        self.wallpaper_preview.set_theme(name)
        self.theme_changed.emit(name)

    def _line(self, form, name, label, settings, secret=False):
        widget = QLineEdit(str(getattr(settings, name)))
        if secret:
            widget.setEchoMode(QLineEdit.EchoMode.Password)
        self.inputs[name] = widget
        form.addRow(label, widget)

    def _choose_wallpaper(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择窗口壁纸', '', '图片 (*.jpg *.jpeg *.png *.webp *.bmp)')
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, '图片不可用', '无法读取这张图片，请选择其他文件。')
            return
        self.wallpaper_path.setText(path)

    def values(self):
        settings = replace(self.initial)
        for name, widget in self.inputs.items():
            setattr(settings, name, widget.text().strip())
        settings.mode = self.mode.currentData()
        settings.selection_enabled = self.selection.isChecked()
        settings.auto_direction = self.auto_direction.isChecked()
        settings.timeout_seconds = self.timeout.value()
        settings.max_text_chars = self.limit.value()
        settings.wallpaper_path = self.wallpaper_path.text().strip()
        settings.window_opacity = self.window_opacity.value()
        settings.color_theme = self.color_theme.currentData()
        settings.validate()
        return settings

    def _accept(self):
        try:
            self.values()
        except ValueError as exc:
            QMessageBox.warning(self, '设置有误', str(exc))
            return
        self.accept()


class ResultWindow(QWidget):
    retry = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('Paper Translator · 翻译结果')
        self.resize(490, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.source_label = QLabel('原文 / OCR 识别结果（可修改）')
        layout.addWidget(self.source_label)
        self.source = QTextEdit()
        self.source.setAcceptRichText(False)
        self.source.setMaximumHeight(110)
        layout.addWidget(self.source)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        row = QHBoxLayout()
        retry, copy, close = QPushButton('重新翻译'), QPushButton('复制译文'), QPushButton('关闭')
        retry.clicked.connect(lambda: self.retry.emit(self.source.toPlainText()))
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.translation))
        close.clicked.connect(self.hide)
        for button in (retry, copy, close):
            row.addWidget(button)
        self.action_buttons = (retry, copy, close)
        layout.addLayout(row)
        self.translation = ''
        self.theme_name = 'dark'
        self._result_colors = result_palette('dark')
        self._theme_start = self._result_colors
        self._theme_target = self._result_colors
        self.theme_transition = QVariantAnimation(self)
        self.theme_transition.setDuration(300)
        self.theme_transition.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.theme_transition.valueChanged.connect(self._theme_frame)
        self.theme_transition.finished.connect(
            lambda: self._render_theme(self._theme_target))
        self.apply_theme('dark', animated=False)

    def _render_theme(self, colors):
        self._result_colors = dict(colors)
        self.setStyleSheet(f'''QWidget {{ background:{colors['background']}; color:{colors['text']}; }}
            QLabel {{ color:{colors['muted']}; font-size:14px; }}
            QTextEdit {{ color:{colors['text']}; background:{colors['panel']}; border:1px solid {colors['border']};
                border-radius:12px; padding:10px; selection-background-color:{colors['accent']}; }}
            QTextEdit:focus {{ border-color:{colors['accent']}; }}
            QPushButton {{ color:{colors['button_text']}; background:{colors['accent']}; border:0;
                border-radius:9px; padding:8px 14px; font-weight:600; }}
            QPushButton:hover {{ background:{colors['accent_hover']}; }}''')

    def _theme_frame(self, progress):
        self._render_theme(blend_palette(
            self._theme_start, self._theme_target, progress))

    def apply_theme(self, name, animated=True):
        name = name if name in THEMES else 'dark'
        target = result_palette(name)
        should_animate = animated and self.isVisible() and name != self.theme_name
        self.theme_name = name
        self.theme_transition.stop()
        if should_animate:
            self._theme_start = dict(self._result_colors)
            self._theme_target = target
            self.theme_transition.setStartValue(0.0)
            self.theme_transition.setEndValue(1.0)
            self.theme_transition.start()
        else:
            self._theme_target = target
            self._render_theme(target)

    def display(self, result):
        self.translation = result.translation
        self.source.setPlainText(result.source)
        self.status.setText('论文模式 · AI 已复核（请结合原文核对）' if result.reviewed else
                            ('论文模式 · 仅初译' if result.mode == 'paper' else '日常模式'))
        sections = [result.translation]
        if result.warning:
            sections.append('提示：' + result.warning)
        if result.ambiguities:
            sections.append('歧义 / 需核对\n' + '\n'.join(result.ambiguities))
        self.output.setPlainText('\n\n'.join(sections))
        self._near_cursor()
        self.show()

    def prepare(self, text):
        self.source.setPlainText(text)
        self.translation = ''
        self.output.clear()
        self.status.setText('正在翻译…')
        self._near_cursor()
        self.show()

    def show_error(self, message):
        self.status.setText('翻译未完成')
        self.output.setPlainText(message)
        self.translation = ''
        self._near_cursor()
        self.show()

    def _near_cursor(self):
        point = QCursor.pos()
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            x = min(max(area.left(), point.x() + 16), max(area.left(), area.right() - self.width()))
            y = min(max(area.top(), point.y() + 16), max(area.top(), area.bottom() - self.height()))
            self.move(x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):
    screenshot = Signal()
    toggle = Signal()
    settings_requested = Signal()
    manual = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Paper Translator')
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(460, 320)
        self.resize(720, 520)
        widget = WallpaperCanvas()
        self.wallpaper = widget
        self.wallpaper.setMouseTracking(True)
        self.wallpaper.installEventFilter(self)
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 18, 30, 30)
        layout.setSpacing(24)
        self.title_bar = WindowTitleBar(self)
        self.settings_button = self.title_bar.settings_button
        self.settings_button.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.title_bar)

        card = QFrame()
        self.card = card
        card.setObjectName('translationCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)
        self.input = SubmitTextEdit()
        self.input.setAcceptRichText(False)
        self.input.setPlaceholderText('输入或粘贴文本  ·  Ctrl + Enter 翻译')
        self.input.submitted.connect(lambda: self.manual.emit(self.input.toPlainText()))
        card_layout.addWidget(self.input)
        layout.addWidget(card, 1)

        # Kept as hidden signal sinks for platform adapters; no status prose is shown on the homepage.
        self.state = QLabel()
        self.platform_status = QLabel()
        self.state.hide()
        self.platform_status.hide()
        self.statusBar().hide()
        self.can_hide_to_tray = False
        self.allow_quit = False
        self._resize_margin = 8
        self.theme_name = 'dark'
        self._main_colors = dict(theme_colors('dark'))
        self._theme_start = self._main_colors
        self._theme_target = self._main_colors
        self.theme_transition = QVariantAnimation(self)
        self.theme_transition.setDuration(300)
        self.theme_transition.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.theme_transition.valueChanged.connect(self._theme_frame)
        self.theme_transition.finished.connect(
            lambda: self._render_theme(self._theme_target))
        self.apply_theme('dark', animated=False)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.title_bar.maximize_button.setText('□')
        else:
            self.showMaximized()
            self.title_bar.maximize_button.setText('❐')

    def resize_edges(self, point):
        if self.isMaximized() or self.isFullScreen():
            return Qt.Edge(0)
        edges = Qt.Edge(0)
        if point.x() < self._resize_margin:
            edges |= Qt.Edge.LeftEdge
        elif point.x() >= self.width() - self._resize_margin:
            edges |= Qt.Edge.RightEdge
        if point.y() < self._resize_margin:
            edges |= Qt.Edge.TopEdge
        elif point.y() >= self.height() - self._resize_margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for_edges(edges):
        if edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge,
                     Qt.Edge.RightEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (Qt.Edge.RightEdge | Qt.Edge.TopEdge,
                     Qt.Edge.LeftEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeBDiagCursor
        if edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            return Qt.CursorShape.SizeHorCursor
        if edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def eventFilter(self, watched, event):
        if watched is self.wallpaper:
            if event.type() == QEvent.Type.MouseMove and not event.buttons():
                point = watched.mapTo(self, event.position().toPoint())
                self.wallpaper.setCursor(self._cursor_for_edges(self.resize_edges(point)))
            elif (event.type() == QEvent.Type.MouseButtonPress and
                  event.button() == Qt.MouseButton.LeftButton):
                point = watched.mapTo(self, event.position().toPoint())
                edges = self.resize_edges(point)
                handle = self.windowHandle()
                if edges and handle and handle.startSystemResize(edges):
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.Leave:
                self.wallpaper.unsetCursor()
        return super().eventFilter(watched, event)

    def refresh(self, settings):
        self.apply_theme(settings.color_theme)
        self.wallpaper.set_appearance(settings.wallpaper_path)
        self.setWindowOpacity(settings.window_opacity / 100)

    def _render_theme(self, colors):
        self._main_colors = dict(colors)
        self.wallpaper.set_theme_colors(colors, self.theme_name)
        self.title_bar.brand.setStyleSheet(
            f"color:{colors['text']}; font-size:22px; font-weight:700; letter-spacing:0.4px;")
        self.title_bar.brand_mark.setStyleSheet(
            f"color:{colors['accent']}; font-size:12px;")
        self.card.setStyleSheet(f'''QFrame#translationCard {{ background:{colors['card']};
            border:1px solid {colors['card_border']}; border-radius:24px; }}''')
        self.input.setStyleSheet(f'''QTextEdit {{ color:{colors['text']};
            background:{colors['input']}; border:1px solid {colors['input_border']};
            border-radius:17px; padding:16px; font-size:16px;
            selection-background-color:{colors['accent']}; }}
            QTextEdit:focus {{ border:2px solid {colors['accent']};
                background:{colors['input_focus']}; }}''')

    def _theme_frame(self, progress):
        self._render_theme(blend_palette(
            self._theme_start, self._theme_target, progress))

    def apply_theme(self, name, animated=True):
        name = name if name in THEMES else 'dark'
        target = theme_colors(name)
        should_animate = animated and self.isVisible() and name != self.theme_name
        self.theme_name = name
        self.title_bar.apply_theme(name)
        self.theme_transition.stop()
        if should_animate:
            self._theme_start = dict(self._main_colors)
            self._theme_target = dict(target)
            self.theme_transition.setStartValue(0.0)
            self.theme_transition.setEndValue(1.0)
            self.theme_transition.start()
        else:
            self._theme_target = dict(target)
            self._render_theme(target)

    def closeEvent(self, event):
        if self.allow_quit:
            event.accept()
            return
        event.ignore()
        if self.can_hide_to_tray:
            self.hide()
        else:
            self.showMinimized()
