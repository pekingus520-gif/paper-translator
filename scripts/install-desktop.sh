#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
launcher="$project_dir/PaperTranslator"
if [[ ! -x "$launcher" ]]; then
  launcher="$project_dir/scripts/run-linux.sh"
fi
icon="$project_dir/assets/paper-translator-icon.png"
if [[ ! -f "$icon" ]]; then
  icon="$project_dir/src/paper_translator/assets/paper-translator-icon.png"
fi
app_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$app_dir"
escaped_launcher="${launcher//\\/\\\\}"
escaped_launcher="${escaped_launcher//\"/\\\"}"
escaped_launcher="${escaped_launcher//\$/\\\$}"
escaped_launcher="${escaped_launcher//\`/\\\`}"
cat > "$app_dir/io.github.papertranslator.App.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Paper Translator
Comment=划词与截图翻译
Exec="$escaped_launcher"
Icon="$icon"
Terminal=false
Categories=Education;
StartupWMClass=PaperTranslator
EOF
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$app_dir"
fi
echo '已添加应用菜单入口。请从应用菜单打开 Paper Translator。'
