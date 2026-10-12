from dataclasses import replace
from pathlib import Path
import tempfile

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage

from .ocr import OCR, OCRError
from .providers import Translator, TranslationError
from .state import RequestGate


class WorkerSignals(QObject):
    done = Signal(int, object, str)
    source_ready = Signal(int, str, str)


class TranslationWorker(QRunnable):
    def __init__(self, token, kind, value, settings, translator, gate, context=''):
        super().__init__()
        self.signals = WorkerSignals()
        self.token, self.kind, self.value = token, kind, value
        self.settings, self.translator, self.gate = settings, translator, gate
        self.context = context

    def run(self):
        result, error = None, ''
        try:
            if not self.gate.accepts(self.token):
                return
            if self.kind == 'image':
                with tempfile.TemporaryDirectory(prefix='paper-translator-shot-') as folder:
                    path = Path(folder) / 'capture.png'
                    if not self.value.save(str(path)):
                        raise OCRError('无法保存本次截图')
                    text = OCR(self.settings.tesseract_path, self.settings.ocr_languages).recognize(path)
            else:
                text = self.value
            if not self.gate.accepts(self.token):
                return
            self.signals.source_ready.emit(self.token, text, self.context)
            result = self.translator.translate(text, self.settings,
                                               cancelled=lambda: not self.gate.accepts(self.token),
                                               **({'context': self.context} if self.context else {}))
        except (TranslationError, OCRError, ValueError) as exc:
            error = str(exc)
        except Exception:
            error = '处理失败，请检查接口配置和 OCR 安装。'
        finally:
            self.signals.done.emit(self.token, result, error)


class TranslationController(QObject):
    result = Signal(object)
    source_ready = Signal(str)
    error = Signal(str)
    status = Signal(str)
    finished = Signal(int)
    enabled_changed = Signal(bool)

    def __init__(self, settings, translator=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.translator = translator or Translator()
        self.gate = RequestGate(settings.enabled)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.busy = False
        self.pending = None
        self._worker = None
        self.last_context = ''

    def apply_settings(self, settings):
        self.settings = settings
        self.pending = None
        self.gate.set_enabled(settings.enabled)
        self.enabled_changed.emit(settings.enabled)

    def set_enabled(self, enabled):
        self.settings.enabled = enabled
        self.pending = None
        self.gate.set_enabled(enabled)
        self.enabled_changed.emit(enabled)
        self.status.emit('翻译已启用' if enabled else '翻译已暂停')

    def submit_text(self, text, context=''):
        if not text.strip():
            return None
        return self._submit('text', text.strip(), context)

    def submit_image(self, image):
        if image.isNull():
            self.error.emit('截图为空，请重新截图')
            return None
        return self._submit('image', QImage(image))

    def _submit(self, kind, value, context=''):
        token = self.gate.issue()
        if token is None:
            return None
        context = context[:4000] if isinstance(context, str) else ''
        job = (token, kind, value, replace(self.settings), context)
        if self.busy:
            self.pending = job
        else:
            self._start(job)
        return token

    def _start(self, job):
        token, kind, value, settings, context = job
        self.busy = True
        self.status.emit('正在识别截图并翻译…' if kind == 'image' else '正在翻译…')
        self._worker = TranslationWorker(token, kind, value, settings, self.translator, self.gate, context)
        self._worker.signals.done.connect(self._done)
        self._worker.signals.source_ready.connect(self._source_ready)
        self.pool.start(self._worker)

    @Slot(int, str, str)
    def _source_ready(self, token, text, context):
        if self.gate.accepts(token):
            self.last_context = context
            self.source_ready.emit(text)

    @Slot(int, object, str)
    def _done(self, token, result, error):
        self.busy = False
        self._worker = None
        if self.gate.accepts(token):
            if error:
                self.error.emit(error)
            elif result:
                self.result.emit(result)
                self.status.emit('翻译完成')
        self.finished.emit(token)
        pending, self.pending = self.pending, None
        if pending and self.gate.accepts(pending[0]):
            self._start(pending)
