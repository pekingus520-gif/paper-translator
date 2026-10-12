#!/usr/bin/env bash
set -euo pipefail
uuid='paper-translator-bridge@local'
gnome-extensions disable "$uuid" || true
gnome-extensions uninstall "$uuid"
echo '已移除 GNOME 取词辅助组件；软件源码和 API 设置不受影响。'
