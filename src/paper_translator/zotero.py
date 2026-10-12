"""Authenticated, loopback-only Zotero reader input; no translation keys here."""
import hmac
import json
import logging
from pathlib import Path
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Signal
from .config import atomic_json, config_directory


class ZoteroBridge(QObject):
    selection = Signal(dict)

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = path or config_directory() / 'zotero.json'
        self.publish_snap = path is None and os.name != 'nt'
        self.published_paths = {self.path}
        self.token = secrets.token_urlsafe(32)
        self.generation = ''
        self.url = ''
        self.server = None
        self.thread = None
        self.lock = threading.Lock()
        self.enabled = False

    def start(self, settings):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.connection.settimeout(2)
                code = 400
                if (self.path != '/selection' or self.headers.get('Origin')
                    or self.headers.get('Host') != bridge.url.removeprefix('http://')
                    or not hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + bridge.token).encode())):
                    code = 403
                else:
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                        if not 0 < size <= 65536:
                            raise ValueError()
                        raw = self.rfile.read(size)
                        value = json.loads(raw.decode('utf-8'))
                        if not isinstance(value, dict):
                            raise ValueError()
                        text, context = value.get('text'), value.get('context', '')
                        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
                            raise ValueError()
                        if not isinstance(context, str) or len(context) > 4000:
                            raise ValueError()
                        with bridge.lock:
                            if not bridge.enabled or value.get('generation') != bridge.generation:
                                code = 409
                            else:
                                bridge.selection.emit({'text': text, 'context': context,
                                                       'generation': bridge.generation})
                                code = 202
                    except (ValueError, UnicodeError, OSError):
                        code = 400
                self.send_response(code)
                self.send_header('Content-Length', '0')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        try:
            self.configure(settings)
        except OSError:
            self.server.server_close()
            self.server = None
            raise
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def configure(self, settings):
        with self.lock:
            self.generation = secrets.token_hex(16)
            self.enabled = settings.enabled and settings.selection_enabled
            metadata = {'url': self.url, 'token': self.token, 'generation': self.generation,
                        'enabled': self.enabled, 'mode': settings.mode}
        if self.server:
            atomic_json(self.path, metadata)
            if os.name != 'nt':
                os.chmod(self.path, 0o600)
            # Snap rewrites HOME and cannot read the host's hidden config folder.
            # Its common directory remains readable across Snap revisions.
            for snap_name in ('zotero', 'zotero-snap'):
                common = Path.home() / 'snap' / snap_name / 'common'
                if self.publish_snap and common.is_dir():
                    target = common / 'paper-translator' / 'zotero.json'
                    try:
                        atomic_json(target, metadata)
                        os.chmod(target, 0o600)
                        self.published_paths.add(target)
                    except OSError:
                        logging.warning('无法写入 Zotero Snap 连接文件：%s', target)


    def close(self):
        with self.lock:
            self.enabled = False
            self.generation = secrets.token_hex(16)
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None
        for path in self.published_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
