#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
  python3 -m venv "$project_dir/.venv" || {
    echo '请先安装虚拟环境支持：sudo apt install python3-venv'
    exit 1
  }
  "$project_dir/.venv/bin/python" -m pip install --disable-pip-version-check -e "$project_dir"
fi
exec "$project_dir/.venv/bin/python" -m paper_translator "$@"
