from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlparse


def config_directory():
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA', str(Path.home()))) / 'PaperTranslator'
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'paper-translator'


def canonical_hotkey(value):
    parts = [x.strip() for x in value.split('+')]
    aliases = {'ctrl': 'Ctrl', 'alt': 'Alt', 'shift': 'Shift',
               'super': 'Meta', 'win': 'Meta', 'meta': 'Meta'}
    if len(parts) < 2 or any(p.lower() not in aliases for p in parts[:-1]):
        raise ValueError('快捷键需要修饰键，例如 Ctrl+Alt+S')
    mods = {aliases[p.lower()] for p in parts[:-1]}
    if len(mods) != len(parts) - 1:
        raise ValueError('快捷键修饰键重复')
    key = parts[-1].upper()
    if not re.fullmatch(r'[A-Z0-9]|F(?:[1-9]|1[0-2])', key):
        raise ValueError('快捷键末尾请使用字母、数字或 F1–F12')
    return '+'.join([m for m in ('Ctrl', 'Alt', 'Shift', 'Meta') if m in mods] + [key])


def validate_url(value):
    p = urlparse(value)
    if not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError('接口地址格式不正确，请勿在地址中包含密钥或查询参数')
    if p.scheme != 'https' and not (p.scheme == 'http' and p.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('远程 API 请使用 HTTPS；本地接口可以使用 HTTP')


@dataclass
class Settings:
    mode: str = 'daily'
    enabled: bool = True
    selection_enabled: bool = True
    main_window_on_top: bool = False
    screenshot_hotkey: str = 'Ctrl+Alt+S'
    toggle_hotkey: str = 'Ctrl+Alt+T'
    baidu_app_id: str = ''
    baidu_key: str = ''
    baidu_url: str = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
    ai_url: str = ''
    ai_key: str = ''
    ai_model: str = ''
    discipline: str = ''
    auto_direction: bool = True
    source_language: str = 'auto'
    target_language: str = 'zh'
    ocr_languages: str = 'eng'
    tesseract_path: str = ''
    timeout_seconds: int = 25
    max_text_chars: int = 3000
    wallpaper_path: str = ''
    window_opacity: int = 92
    color_theme: str = 'dark'

    def validate(self):
        if self.mode not in ('daily', 'paper'):
            raise ValueError('模式必须是日常或论文')
        for name in ('enabled', 'selection_enabled', 'main_window_on_top', 'auto_direction'):
            if type(getattr(self, name)) is not bool:
                raise ValueError('开关设置格式错误')
        self.screenshot_hotkey = canonical_hotkey(self.screenshot_hotkey)
        self.toggle_hotkey = canonical_hotkey(self.toggle_hotkey)
        if self.screenshot_hotkey == self.toggle_hotkey:
            raise ValueError('截图和总开关不能使用相同快捷键')
        if not 5 <= self.timeout_seconds <= 120:
            raise ValueError('超时必须在 5–120 秒之间')
        if not 1 <= self.max_text_chars <= 10000:
            raise ValueError('文字上限必须在 1–10000 之间')
        if not isinstance(self.wallpaper_path, str):
            raise ValueError('壁纸路径格式错误')
        if type(self.window_opacity) is not int or not 30 <= self.window_opacity <= 100:
            raise ValueError('窗口透明度必须在 30–100 之间')
        if self.color_theme not in ('dark', 'light'):
            raise ValueError('颜色主题必须是深色或浅色')
        if not re.fullmatch(r'[A-Za-z_]+(?:\+[A-Za-z_]+)*', self.ocr_languages):
            raise ValueError('OCR 语言格式例如 eng 或 eng+chi_sim')
        validate_url(self.baidu_url)
        if self.ai_url:
            validate_url(self.ai_url)


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.tmp-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class SecureKeyring:
    """Only use known OS credential vaults, never plaintext fallback backends."""
    def __init__(self):
        import keyring
        backend = keyring.get_keyring()
        candidates = getattr(backend, 'backends', [backend])
        safe = ('keyring.backends.SecretService', 'keyring.backends.Windows',
                'keyring.backends.macOS', 'keyring.backends.kwallet')
        self.backend = next((b for b in candidates if type(b).__module__.startswith(safe)), None)

    def _check(self):
        if self.backend is None:
            raise RuntimeError('No secure credential vault')

    def get_password(self, service, name):
        self._check()
        return self.backend.get_password(service, name)

    def set_password(self, service, name, value):
        self._check()
        self.backend.set_password(service, name, value)

    def delete_password(self, service, name):
        self._check()
        try:
            self.backend.delete_password(service, name)
        except Exception:
            if self.backend.get_password(service, name):
                raise


class ConfigStore:
    service = 'PaperTranslator'
    secret_names = ('baidu_key', 'ai_key')

    def __init__(self, path=None, keyring_backend=None):
        self.path = Path(path) if path else config_directory() / 'settings.json'
        self._session = {}
        self.warning = ''
        try:
            self.keyring = keyring_backend if keyring_backend is not None else SecureKeyring()
        except Exception:
            self.keyring = None

    def load(self):
        data = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding='utf-8'))
                if 'window_opacity' not in raw and 'wallpaper_opacity' in raw:
                    raw['window_opacity'] = max(30, min(100, raw['wallpaper_opacity']))
                allowed = {f.name for f in fields(Settings)} - set(self.secret_names)
                data = {k: v for k, v in raw.items() if k in allowed}
                s = Settings(**data)
                s.validate()
            except (ValueError, TypeError, AttributeError):
                self.warning = '配置文件损坏，已使用默认设置；原文件未覆盖。'
                s = Settings()
        else:
            s = Settings()
        for name in self.secret_names:
            if name in self._session:
                value = self._session[name]
            else:
                try:
                    value = self.keyring.get_password(self.service, name) or ''
                except Exception:
                    value = ''
            setattr(s, name, value)
        return s

    def save(self, settings):
        settings.validate()
        if settings.wallpaper_path:
            source = Path(settings.wallpaper_path)
            suffix = source.suffix.lower()
            if suffix not in ('.jpg', '.jpeg', '.png', '.webp', '.bmp') or not source.is_file():
                raise ValueError('请选择有效的 JPG、PNG、WebP 或 BMP 图片')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            target = self.path.parent / ('wallpaper' + suffix)
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            settings.wallpaper_path = str(target)
        warning = ''
        data = asdict(settings)
        for name in self.secret_names:
            value = data.pop(name)
            self._session[name] = value
            try:
                if value:
                    self.keyring.set_password(self.service, name, value)
                else:
                    self.keyring.delete_password(self.service, name)
            except Exception:
                warning = '系统密钥库不可用：API 密钥仅保留到本次程序退出，下次需重新填写。'
        atomic_json(self.path, data)
        self.warning = warning
        return warning
