import json
import os

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .config import config_directory


def socket_name():
    if os.name == 'nt':
        import getpass
        return 'PaperTranslator-' + getpass.getuser()
    return str(config_directory() / 'commands.sock')


def send_command(name, command):
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(250):
        return False
    socket.write((json.dumps(command, ensure_ascii=False) + '\n').encode())
    socket.flush()
    ok = socket.waitForBytesWritten(500) if socket.bytesToWrite() else True
    socket.disconnectFromServer()
    return ok


class LocalCommandServer(QObject):
    command = Signal(dict)

    def __init__(self, name=None, parent=None):
        super().__init__(parent)
        self.name = name or socket_name()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)
        self.clients = set()
        self.timers = {}

    def start(self):
        probe = QLocalSocket()
        probe.connectToServer(self.name)
        if probe.waitForConnected(250):
            probe.abort()
            raise RuntimeError('程序已经在运行')
        if self.server.listen(self.name):
            return
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            raise RuntimeError('无法建立本地通信，请检查配置目录权限')

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.clients.add(socket)
            socket._buffer = bytearray()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._release(s))
            timer = QTimer(self)
            self.timers[socket] = timer
            timer.setSingleShot(True)
            # Accepted sockets are C++-created: binding abort directly causes
            # PySide dynamic-slot warnings when an external client closes quickly.
            timer.timeout.connect(lambda s=socket: self._expire(s))
            timer.start(2000)
            self._read(socket)

    def _expire(self, socket):
        if socket in self.clients:
            socket.abort()

    def _read(self, socket):
        socket._buffer.extend(bytes(socket.readAll()))
        if len(socket._buffer) > 65536:
            socket.abort()
            return
        if b'\n' not in socket._buffer:
            return
        try:
            value = json.loads(socket._buffer.split(b'\n', 1)[0].decode('utf-8'))
            if not isinstance(value, dict):
                raise ValueError()
            name = value.get('command')
            if name == 'selection':
                if not isinstance(value.get('text'), str) or not 0 < len(value['text']) <= 10000:
                    raise ValueError()
            elif name == 'bridge':
                if not isinstance(value.get('status', ''), str) or len(value.get('status', '')) > 1000:
                    raise ValueError()
            elif name in ('screenshot_native', 'screenshot_file', 'screenshot_cancel'):
                capture_id = value.get('capture_id')
                if not isinstance(capture_id, str) or not 0 < len(capture_id) <= 100:
                    raise ValueError()
                if name == 'screenshot_file':
                    path = value.get('path')
                    if not isinstance(path, str) or not 0 < len(path) <= 4096:
                        raise ValueError()
            elif name not in ('screenshot', 'toggle', 'show'):
                raise ValueError()
            self.command.emit(value)
        except (ValueError, UnicodeError):
            pass
        socket.disconnectFromServer()

    def _release(self, socket):
        timer = self.timers.pop(socket, None)
        if timer is not None:
            timer.stop()
            timer.timeout.disconnect()
            timer.deleteLater()
        self.clients.discard(socket)
        socket.readyRead.disconnect()
        socket.disconnected.disconnect()
        socket.deleteLater()

    def close(self):
        for socket in list(self.clients):
            socket.abort()
        self.server.close()
