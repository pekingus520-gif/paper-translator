#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v gnome-shell >/dev/null || ! command -v gnome-extensions >/dev/null; then
  echo '此辅助组件仅用于 GNOME 桌面。Windows 和 Linux X11 无需安装。'
  exit 1
fi
if ! command -v glib-compile-schemas >/dev/null; then
  echo '缺少 glib-compile-schemas，请安装 libglib2.0-bin。'
  exit 1
fi
uuid='paper-translator-bridge@local'
target_dir="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$uuid"
mkdir -p "$target_dir/schemas"
cp "$project_dir/gnome-bridge/metadata.json" "$project_dir/gnome-bridge/extension.js" "$project_dir/gnome-bridge/selection.js" "$target_dir/"
cp "$project_dir/gnome-bridge/schemas/"*.xml "$target_dir/schemas/"
glib-compile-schemas --strict "$target_dir/schemas"
echo "已安装辅助组件：$target_dir"
if gnome-extensions enable "$uuid"; then
  echo '已启用。请启动翻译软件，检查主窗口是否显示已连接。'
else
  echo 'GNOME 尚未发现新组件：请注销并重新登录，然后运行：'
  echo "gnome-extensions enable $uuid"
fi
