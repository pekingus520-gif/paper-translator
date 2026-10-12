"""Build the installable Zotero plugin using the Python standard library."""
from pathlib import Path
import argparse
import json
import zipfile
from urllib.parse import urlparse

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'zotero-plugin/manifest.json').read_text())
parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=root / 'dist' / f"PaperTranslator-Zotero-{manifest['version']}.xpi")
parser.add_argument('--update-url', default=manifest['applications']['zotero']['update_url'], help='HTTPS feed; default .invalid placeholder means manual distribution only')
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
# Zotero validates update security at installation, even for manual distribution.
# .invalid is deliberately unhosted, not an advertised automatic update service.
app = manifest['applications']['zotero']
url = urlparse(args.update_url)
if url.scheme != 'https' or not url.hostname or url.username or url.password:
    parser.error('Zotero update_url must use HTTPS')
app['update_url'] = args.update_url
with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    archive.write(root / 'zotero-plugin/bootstrap.js', 'bootstrap.js')
print(args.output)
