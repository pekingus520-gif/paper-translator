#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
python_bin="${TRANSLATOR_PYTHON:-$project_dir/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python3 -m venv "$project_dir/.venv"
fi
"$python_bin" -m pip install -e '.[dev]'
"$python_bin" -m PyInstaller --noconfirm --clean --name PaperTranslator --paths src scripts/entrypoint.py
echo "完成：$project_dir/dist/PaperTranslator/PaperTranslator"
echo '发布时请保留整个文件夹；截图 OCR 需另行安装 Tesseract。'
