from PySide6.QtCore import QObject, Signal

from ..config import canonical_hotkey


def hotkey_parts(value):
    parts = canonical_hotkey(value).split('+')
    return set(parts[:-1]), parts[-1]


def gnome_accelerator(value):
    mods, key = hotkey_parts(value)
    names = {'Ctrl': '<Control>', 'Alt': '<Alt>', 'Shift': '<Shift>', 'Meta': '<Super>'}
    return ''.join(names[m] for m in ('Ctrl', 'Alt', 'Shift', 'Meta') if m in mods) + (key if key.startswith('F') and len(key) > 1 else key.lower())


class InputAdapter(QObject):
    selection = Signal(str)
    screenshot = Signal()
    toggle = Signal()
    status = Signal(str)

    def configure(self, settings):
        self.settings = settings

    def start(self):
        pass

    def stop(self):
        pass
