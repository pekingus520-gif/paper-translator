import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse
import zipfile


def test_plugin_source_manifest_has_required_update_url():
    root = Path(__file__).resolve().parents[1]
    app = json.loads((root / 'zotero-plugin/manifest.json').read_text())['applications']['zotero']
    assert app.get('update_url'), 'Zotero rejects manifests without applications.zotero.update_url'
    assert urlparse(app['update_url']).scheme == 'https', 'Zotero requires HTTPS update URLs'


def test_built_xpi_has_https_update_url(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'plugin.xpi'
    subprocess.run([sys.executable, str(root / 'scripts/build-zotero.py'), '--output', str(output)], check=True)
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        app = manifest['applications']['zotero']
        assert app.get('update_url'), 'Missing required update URL'
        parsed = urlparse(app['update_url'])
        assert parsed.scheme == 'https'
        assert parsed.hostname
        assert app['strict_max_version'] == '9.0.*'
        assert archive.testzip() is None
