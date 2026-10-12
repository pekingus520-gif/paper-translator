import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from paper_translator.config import Settings
from paper_translator.zotero import ZoteroBridge


def post(bridge, payload, token=None, **headers):
    request = Request(bridge.url + '/selection', json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (token or bridge.token), **headers})
    try:
        with urlopen(request, timeout=3) as response:
            return response.status
    except HTTPError as exc:
        code = exc.code
        exc.close()
        return code


@pytest.fixture
def bridge(tmp_path):
    bridge = ZoteroBridge(tmp_path / 'zotero.json')
    bridge.start(Settings())
    yield bridge
    bridge.close()


def test_bridge_delivers_selection_and_context(bridge, spin):
    received = []
    bridge.selection.connect(received.append)
    payload = {'text': 'attention', 'context': 'neural network attention', 'generation': bridge.generation}
    assert post(bridge, payload) == 202
    spin(lambda: bool(received))
    assert received[0] == payload
    config = json.loads(bridge.path.read_text())
    assert config['url'].startswith('http://127.0.0.1:')
    assert 'baidu_key' not in config and 'ai_key' not in config
    if os.name != 'nt':
        assert bridge.path.stat().st_mode & 0o777 == 0o600


def test_bridge_rejects_unauthenticated_browser_and_oversized_context(bridge):
    payload = {'text': 'x', 'generation': bridge.generation}
    assert post(bridge, payload, token='incorrect') == 403
    assert post(bridge, payload, Origin='https://example.com') == 403
    assert post(bridge, {**payload, 'context': 'x' * 4001}) == 400
    assert post(bridge, {**payload, 'context': 123}) == 400


def test_bridge_pause_and_generation_drop_old_requests(bridge):
    old = bridge.generation
    bridge.configure(Settings(enabled=False))
    assert post(bridge, {'text': 'x', 'generation': bridge.generation}) == 409
    bridge.configure(Settings())
    assert post(bridge, {'text': 'x', 'generation': old}) == 409
    assert post(bridge, {'text': 'x', 'generation': bridge.generation}) == 202


def test_bridge_shutdown_removes_discovery_file(tmp_path):
    bridge = ZoteroBridge(tmp_path / 'zotero.json')
    bridge.start(Settings())
    assert bridge.path.exists()
    bridge.close()
    assert not bridge.path.exists()
    bridge.close()


def test_desktop_drops_queued_zotero_selection_after_pause_and_passes_context():
    from types import SimpleNamespace
    from paper_translator.app import DesktopApplication
    desktop = DesktopApplication.__new__(DesktopApplication)
    desktop.zotero = SimpleNamespace(generation='current')
    desktop.capture_lock = False
    desktop.settings = Settings(mode='paper')
    calls = []
    desktop.controller = SimpleNamespace(submit_text=lambda text, context='': calls.append((text, context)))
    desktop.zotero_selection({'text': 'old', 'context': 'wrong', 'generation': 'old'})
    desktop.zotero_selection({'text': 'term', 'context': 'paragraph', 'generation': 'current'})
    assert calls == [('term', 'paragraph')]
    desktop.settings.enabled = False
    desktop.zotero_selection({'text': 'paused', 'generation': 'current'})
    assert len(calls) == 1
    desktop.settings.enabled = True
    desktop.settings.mode = 'daily'
    desktop.zotero_selection({'text': 'fast', 'context': 'omit', 'generation': 'current'})
    assert calls[-1] == ('fast', '')


def test_shipped_plugin_uses_real_http_bridge_with_pdf_context(bridge, spin):
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is only required for the plugin integration test')
    bridge.configure(Settings(mode='paper'))
    received = []
    bridge.selection.connect(received.append)
    result = subprocess.run([node, str(Path(__file__).with_name('zotero_host.mjs')), str(bridge.path)],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    spin(lambda: bool(received))
    assert received[0]['text'] == 'attention'
    assert received[0]['context'] == 'Neural networks use attention to weight the values.'


@pytest.mark.parametrize('snap_name', ['zotero', 'zotero-snap'])
def test_snap_discovery_tracks_pause_and_shutdown(tmp_path, monkeypatch, snap_name):
    from pathlib import Path
    import paper_translator.zotero as module
    home = tmp_path / 'home'
    common = home / 'snap' / snap_name / 'common'
    common.mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setattr(module, 'config_directory', lambda: home / '.config/paper-translator')
    bridge = ZoteroBridge()
    snap_file = common / 'paper-translator/zotero.json'
    try:
        bridge.start(Settings())
        assert snap_file.read_bytes() == bridge.path.read_bytes()
        assert snap_file.stat().st_mode & 0o777 == 0o600
        first = json.loads(snap_file.read_text())['generation']
        bridge.configure(Settings(enabled=False))
        paused = json.loads(snap_file.read_text())
        assert not paused['enabled'] and paused['generation'] != first
        assert snap_file.read_bytes() == bridge.path.read_bytes()
    finally:
        bridge.close()
    assert not snap_file.exists()
    assert not bridge.path.exists()
