import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


class OCRError(Exception):
    pass


class OCR:
    def __init__(self, executable='', languages='eng', timeout=30):
        self.executable = executable or shutil.which('tesseract') or ''
        self.tessdata = ''
        bundled = Path(getattr(sys, '_MEIPASS', '')) / 'ocr' / ('tesseract.exe' if os.name == 'nt' else 'tesseract')
        if not self.executable and hasattr(sys, '_MEIPASS') and bundled.is_file():
            self.executable = str(bundled)
            self.tessdata = str(bundled.parent / 'tessdata')
        if not self.executable and os.name == 'nt':
            candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR/tesseract.exe'
            if candidate.exists():
                self.executable = str(candidate)
        self.languages = languages
        self.timeout = timeout

    def recognize(self, image_path):
        if not self.executable or not Path(self.executable).is_file():
            raise OCRError('未找到 Tesseract，请安装 OCR 引擎并在设置中填写路径。')
        from PIL import Image, ImageOps
        with tempfile.TemporaryDirectory(prefix='paper-translator-ocr-') as folder:
            target = Path(folder) / 'input.png'
            try:
                with Image.open(image_path) as image:
                    if image.width * image.height > 40_000_000:
                        raise OCRError('截图过大，请缩小识别区域')
                    image = ImageOps.autocontrast(image.convert('L'))
                    if image.width < 1600:
                        image = image.resize((image.width * 2, image.height * 2))
                    image.save(target)
            except (OSError, ValueError):
                raise OCRError('无法读取截图，请重新截图') from None
            try:
                environment = os.environ.copy()
                if self.tessdata:
                    environment['TESSDATA_PREFIX'] = self.tessdata
                result = subprocess.run([self.executable, str(target), 'stdout', '-l', self.languages,
                                         '--psm', '6'], capture_output=True, timeout=self.timeout,
                                        creationflags=0x08000000 if os.name == 'nt' else 0, env=environment)
            except subprocess.TimeoutExpired:
                raise OCRError('OCR 超时，请缩小截图区域') from None
            except OSError:
                raise OCRError('无法运行 Tesseract，请检查 OCR 路径') from None
            if result.returncode:
                raise OCRError(f'OCR 失败，请检查 Tesseract 及语言包：{self.languages}')
            text = result.stdout.decode('utf-8', errors='replace').strip()
            if not text:
                raise OCRError('截图中未识别到文字，请重新选择清晰的文字区域')
            return text
