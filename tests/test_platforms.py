import pytest

from paper_translator.platforms.common import hotkey_parts, gnome_accelerator
from paper_translator.platforms.wayland import WaylandAdapter
from paper_translator.config import Settings


def test_hotkeys_have_consistent_platform_meaning():
    assert hotkey_parts('shift+CTRL+s') == ({'Ctrl', 'Shift'}, 'S')
    assert gnome_accelerator('Ctrl+Alt+S') == '<Control><Alt>s'
    assert gnome_accelerator('Win+F8') == '<Super>F8'
    with pytest.raises(ValueError):
        hotkey_parts('Ctrl+Alt+')


def test_wayland_publishes_only_non_secret_bridge_settings(qapp, tmp_path):
    import json
    adapter = WaylandAdapter(tmp_path / 'bridge.json', '/tmp/test.sock')
    s = Settings(baidu_key='secret', ai_key='other-secret', enabled=False)
    adapter.configure(s)
    value = json.loads((tmp_path / 'bridge.json').read_text())
    assert value['enabled'] is False
    assert value['screenshot'] == '<Control><Alt>s'
    assert value['toggle'] == '<Control><Alt>t'
    assert value['pin_main'] is False
    assert value['socket'] == '/tmp/test.sock'
    assert 'secret' not in json.dumps(value)
    before = value['generation']
    adapter.configure(Settings(enabled=True, main_window_on_top=True, screenshot_hotkey='Alt+B',
                               toggle_hotkey='Ctrl+Alt+Z'))
    resumed = json.loads((tmp_path / 'bridge.json').read_text())
    assert resumed['generation'] != before
    assert resumed['screenshot'] == '<Alt>b'
    assert resumed['toggle'] == '<Control><Alt>z'
    assert resumed['pin_main'] is True
    adapter.stop()
    assert json.loads((tmp_path / 'bridge.json').read_text())['running'] is False


def test_unresponsive_input_process_can_be_stopped():
    import multiprocessing
    from paper_translator.platforms.process import stop_process
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_unresponsive_process, args=(child,), daemon=True)
    process.start()
    assert parent.poll(5)
    assert parent.recv() == 'ready'
    stop_process(process, parent, timeout=0.1)
    assert not process.is_alive()


def test_x11_reconfigure_primes_pending_selection(qapp):
    from paper_translator.platforms.x11 import X11Adapter
    adapter = X11Adapter()
    adapter.debouncer.feed('pending selection', 0)
    adapter.configure(Settings(enabled=False))
    adapter.configure(Settings(enabled=True))
    assert adapter.debouncer.feed('pending selection', 1000) is None
    assert adapter.debouncer.feed('pending selection', 2000) is None


def _unresponsive_process(connection):
    import time
    connection.send('ready')
    time.sleep(60)
