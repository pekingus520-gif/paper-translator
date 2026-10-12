import uuid

from PySide6.QtCore import QObject, QRect, Qt, QTimer, QUrl, Signal, Slot, SLOT
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


class RegionOverlay(QWidget):
    captured = Signal(object)
    cancelled = Signal()

    def __init__(self, pixmap, geometry):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.pixmap = pixmap
        self.setGeometry(geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.origin = None
        self.selection = QRect()
        self._ended = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 70))
        if not self.selection.isEmpty():
            p.drawPixmap(self.selection, self.pixmap, self._pixel_rect(self.selection))
            p.setPen(QPen(QColor('white'), 2))
            p.drawRect(self.selection)
        p.setPen(QColor('white'))
        p.drawText(20, 35, '拖动框选文字区域，Esc 取消（每次选择一个屏幕内的区域）')

    def _pixel_rect(self, rect):
        ratio = self.pixmap.devicePixelRatio()
        return QRect(round(rect.x() * ratio), round(rect.y() * ratio),
                     round(rect.width() * ratio), round(rect.height() * ratio))

    def crop(self, rect):
        return self.pixmap.toImage().copy(self._pixel_rect(rect.intersected(self.rect())))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.origin is not None:
            self.selection = QRect(self.origin, event.position().toPoint()).normalized().intersected(self.rect())
            self.origin = None
            if self.selection.width() >= 4 and self.selection.height() >= 4:
                self._ended = True
                self.captured.emit(self.crop(self.selection))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()

    def cancel(self):
        if not self._ended:
            self._ended = True
            self.cancelled.emit()
        self.hide()


class RegionCapture(QObject):
    captured = Signal(object)
    cancelled = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlays = []

    def start(self):
        if self.overlays:
            return
        screens = [(screen.grabWindow(0), screen.geometry()) for screen in QApplication.screens()]
        if not screens or any(pixmap.isNull() for pixmap, _ in screens):
            self.error.emit('无法截取屏幕，请检查系统截图权限')
            return
        for pixmap, geometry in screens:
            overlay = RegionOverlay(pixmap, geometry)
            overlay.captured.connect(self._finish)
            overlay.cancelled.connect(self.cancel)
            self.overlays.append(overlay)
            overlay.show()
        self.overlays[0].activateWindow()

    def _close(self):
        for overlay in self.overlays:
            overlay.hide()
            overlay.deleteLater()
        self.overlays = []

    def _finish(self, image):
        self._close()
        self.captured.emit(image)

    def cancel(self):
        if self.overlays:
            self._close()
            self.cancelled.emit()


class PortalCapture(QObject):
    """Wayland screenshots are obtained through the desktop's consent UI."""
    path_ready = Signal(str)
    cancelled = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtDBus import QDBusConnection
        self.bus = QDBusConnection.sessionBus()
        self.waiting = False
        self.request_path = ''
        self.watcher = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    def start(self):
        from PySide6.QtDBus import QDBusMessage, QDBusVariant, QDBusPendingCallWatcher
        if self.waiting:
            return
        if not self.bus.isConnected():
            self.error.emit('无法连接桌面截图服务')
            return
        token = 'shot_' + uuid.uuid4().hex
        sender = self.bus.baseService().lstrip(':').replace('.', '_')
        self.request_path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
        self.waiting = True
        connected = self.bus.connect('org.freedesktop.portal.Desktop', self.request_path,
                                    'org.freedesktop.portal.Request', 'Response', self,
                                    SLOT('response(uint,QVariantMap,QDBusMessage)'))
        if not connected:
            self.waiting = False
            self.error.emit('无法订阅桌面截图结果')
            return
        message = QDBusMessage.createMethodCall('org.freedesktop.portal.Desktop',
                    '/org/freedesktop/portal/desktop', 'org.freedesktop.portal.Screenshot', 'Screenshot')
        message.setArguments(['', {'handle_token': QDBusVariant(token),
                                  'interactive': QDBusVariant(True), 'modal': QDBusVariant(False)}])
        self.watcher = QDBusPendingCallWatcher(self.bus.asyncCall(message), self)
        self.watcher.finished.connect(self._called)
        self.timer.start(120000)

    def _called(self, watcher):
        if watcher is not self.watcher:
            watcher.deleteLater()
            return
        from PySide6.QtDBus import QDBusMessage
        reply = watcher.reply()
        if reply.type() == QDBusMessage.MessageType.ErrorMessage and self.waiting:
            self._cleanup()
            self.error.emit('桌面截图服务不可用或权限被拒绝，请检查 xdg-desktop-portal')
        watcher.deleteLater()

    def _cleanup(self):
        if self.request_path:
            self.bus.disconnect('org.freedesktop.portal.Desktop', self.request_path,
                                'org.freedesktop.portal.Request', 'Response', self,
                                SLOT('response(uint,QVariantMap,QDBusMessage)'))
        self.waiting = False
        self.watcher = None
        self.timer.stop()

    @Slot('uint', 'QVariantMap', 'QDBusMessage')
    def response(self, code, results, message=None):
        if not self.waiting:
            return
        if message is not None and message.path() != self.request_path:
            return
        self._cleanup()
        if code == 1:
            self.cancelled.emit()
        elif code != 0:
            self.error.emit('截图失败或被桌面服务拒绝')
        else:
            value = results.get('uri', '')
            if not isinstance(value, str):
                self.error.emit('截图服务返回的文件地址无效')
                return
            uri = QUrl(value)
            if not uri.isLocalFile():
                self.error.emit('截图服务未返回本地图片')
                return
            self.path_ready.emit(uri.toLocalFile())

    def cancel(self):
        if not self.waiting:
            return
        from PySide6.QtDBus import QDBusMessage
        message = QDBusMessage.createMethodCall('org.freedesktop.portal.Desktop', self.request_path,
                                                'org.freedesktop.portal.Request', 'Close')
        self.bus.asyncCall(message)
        self._cleanup()
        self.cancelled.emit()

    def _timeout(self):
        self.cancel()
        self.error.emit('截图等待超时，请重新触发截图')
