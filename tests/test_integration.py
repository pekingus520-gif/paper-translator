from pathlib import Path
import json

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage

from paper_translator.config import Settings
from paper_translator.controller import TranslationController
from paper_translator.ocr import OCR
from paper_translator.capture import PortalCapture


def test_screenshot_ocr_to_translation_with_real_local_http(qapp, spin, tmp_path):
    # A real executable provides OCR output; network contract goes through a real server.
    import os
    if os.name == 'nt':
        import pytest
        pytest.skip('POSIX test OCR executable')
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    from urllib.parse import parse_qs
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            bodies.append(parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode()))
            payload = json.dumps({'trans_result': [{'dst': '注意力机制'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    binary = tmp_path / 'ocr'
    binary.write_text('#!/bin/sh\nprintf "Attention mechanism\\n"\n')
    binary.chmod(0o700)
    try:
        settings = Settings(baidu_app_id='123', baidu_key='secret',
                            baidu_url=f'http://127.0.0.1:{server.server_port}/baidu', tesseract_path=str(binary))
        controller = TranslationController(settings)
        results = []
        controller.result.connect(results.append)
        image = QImage(200, 100, QImage.Format.Format_RGB32)
        image.fill(0xffffffff)
        controller.submit_image(image)
        spin(lambda: bool(results))
        assert bodies[0]['q'] == ['Attention mechanism']
        assert results[0].source == 'Attention mechanism'
        assert results[0].translation == '注意力机制'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_portal_success_delivers_local_path(qapp, tmp_path):
    capture = PortalCapture()
    path = tmp_path / 'space in name.png'
    received = []
    capture.path_ready.connect(received.append)
    capture.waiting = True
    capture.response(0, {'uri': QUrl.fromLocalFile(str(path)).toString()})
    assert received == [str(path)]
