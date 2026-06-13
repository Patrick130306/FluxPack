#!/bin/bash
""" 2>/dev/null; # -*- mode: shell -*-
# FluxPack Linux 安装脚本
# 用法: bash install.sh [--user|--system]

set -e

MODE="${1:---user}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔══════════════════════════════════════════╗"
echo "║     FluxPack Linux 安装                  ║"
echo "╚══════════════════════════════════════════╝"

# ── 检查 Python ──
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        VER=$($cmd --version 2>&1 | grep -oP '\d+\.\d+')
        if (( $(echo "$VER >= 3.8" | bc -l 2>/dev/null || echo 0) )); then
            PYTHON=$cmd
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "❌ 需要 Python 3.8+"
    echo "   安装: sudo apt install python3 python3-pip"
    exit 1
fi
echo "✅ Python: $($PYTHON --version)"

# ── 安装依赖 ──
echo ""
echo "📦 安装依赖..."
$PYTHON -m pip install -r "$SCRIPT_DIR/requirements.txt" -q 2>&1 | tail -1 || true

# ── 创建桌面入口 ──
echo ""
echo "🖥️  创建桌面入口..."

DESKTOP_DIR="$HOME/.local/share/applications"
if [ "$MODE" = "--system" ]; then
    DESKTOP_DIR="/usr/share/applications"
fi
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/fluxpack.desktop" << EOF
[Desktop Entry]
Name=FluxPack
Comment=轻量压缩包管理器
Exec=$PYTHON $SCRIPT_DIR/run_launcher.py %F
Icon=$SCRIPT_DIR/icon.png
Terminal=false
Type=Application
Categories=Utility;Archiving;Compression;
MimeType=application/x-7z-compressed;application/zip;application/x-rar;application/x-tar;application/gzip;
StartupNotify=true
EOF

chmod +x "$DESKTOP_DIR/fluxpack.desktop"

# ── Nautilus 右键菜单脚本 ──
echo ""
echo "🖱️  安装 Nautilus 右键菜单..."

NAUTILUS_SCRIPT_DIR="$HOME/.local/share/nautilus/scripts"
mkdir -p "$NAUTILUS_SCRIPT_DIR"

# 压缩脚本
cat > "$NAUTILUS_SCRIPT_DIR/FluxPack压缩" << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
python3 -c "
import sys, os
sys.path.insert(0, os.path.expanduser('~/FluxPack/src'))
from core.formats import open_archive
for f in sys.argv[1:]:
    p = Path(f)
    dst = p.parent / p.stem
    dst.mkdir(exist_ok=True)
    open_archive(p).extract(dst)
    print(f'✅ 已解压 {p.name} → {dst}')
" "$@"
SCRIPT

# 解压脚本
cat > "$NAUTILUS_SCRIPT_DIR/FluxPack解压" << 'SCRIPT'
#!/usr/bin/env python3
"""Nautilus 脚本: 用 FluxPack 解压"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from pathlib import Path
from src.core.formats import open_archive

for arg in sys.argv[1:]:
    p = Path(arg)
    dst = p.parent / p.stem
    dst.mkdir(parents=True, exist_ok=True)
    try:
        open_archive(p).extract(dst)
        print(f"✅ {p.name} → {dst}")
    except Exception as e:
        print(f"❌ {p.name}: {e}")

input("按 Enter 退出...")
SCRIPT

chmod +x "$NAUTILUS_SCRIPT_DIR/FluxPack压缩" "$NAUTILUS_SCRIPT_DIR/FluxPack解压"

# ── 更新 MIME 数据库 ──
echo ""
echo "🔄 更新 MIME 数据库..."
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi
if command -v xdg-mime &>/dev/null; then
    xdg-mime default fluxpack.desktop application/x-7z-compressed 2>/dev/null || true
    xdg-mime default fluxpack.desktop application/zip 2>/dev/null || true
fi

# ── 创建 CLI 链接 ──
echo ""
echo "🔗 创建命令行链接..."
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/fluxpack" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
$PYTHON run_launcher.py "\$@"
EOF
chmod +x "$HOME/.local/bin/fluxpack"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ FluxPack 安装完成!                   ║"
echo "║                                          ║"
echo "║   命令行: fluxpack <命令>                 ║"
echo "║   GUI:    fluxpack gui                   ║"
echo "║   或从应用菜单启动 FluxPack               ║"
echo "║                                          ║"
echo "║   右键菜单: Nautilus 中选文件→脚本        ║"
echo "╚══════════════════════════════════════════╝"
