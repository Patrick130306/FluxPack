"""右键菜单 / 压缩竞赛 / 批量密码解锁"""

import os
import sys
import time
import json
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Callable
from collections import defaultdict

from .formats import open_archive, detect_format, ZipArchive, SevenZipArchive, TarGzArchive
from .archive import Archive


# ═══════════════════════════════════════════════════════════════════
# 1. 🖱 右键菜单集成 (Windows 注册表)
# ═══════════════════════════════════════════════════════════════════

# FluxPack 入口脚本路径（自动检测）
def _get_fluxpack_script() -> str:
    """获取 fluxpack 脚本路径"""
    # 优先找同目录下的 cli.py
    cli = Path(__file__).parent.parent / "ui" / "cli.py"
    if cli.exists():
        return f'python "{cli}"'
    # 退一步找 main.py
    main = Path(__file__).parent.parent / "main.py"
    if main.exists():
        return f'python "{main}"'
    return "fluxpack"


SHELL_MENU_ITEMS = [
    {
        "name": "FluxPackCompress",
        "display": "用 FluxPack 压缩(&F)",
        "icon": "",
        "command": f'"{sys.executable}" -c "from src.core.power import _context_menu_compress; _context_menu_compress([\\\"%1\\\"])"',
        "description": "使用 FluxPack 多算法混合压缩",
        "extends": [r"*\shell", r"Directory\shell"],
    },
    {
        "name": "FluxPackExtract",
        "display": "用 FluxPack 解压(&E)",
        "icon": "",
        "command": f'"{sys.executable}" -c "from src.core.power import _context_menu_extract; _context_menu_extract([\\\"%1\\\"])"',
        "description": "使用 FluxPack 快速解压",
        "extends": [r"*\shell"],
    },
    {
        "name": "FluxPackBattle",
        "display": "格式竞赛(&B)...",
        "icon": "",
        "command": f'"{sys.executable}" -c "from src.core.power import _context_menu_battle; _context_menu_battle([\\\"%1\\\"])"',
        "description": "多格式压缩对比，找出最优方案",
        "extends": [r"*\shell"],
    },
]


def install_context_menu() -> Tuple[bool, str]:
    """安装右键菜单"""
    if sys.platform == "win32":
        return _install_context_menu_windows()
    elif sys.platform == "linux":
        return _install_context_menu_linux()
    return False, f"不支持的平台: {sys.platform}"


def _install_context_menu_linux() -> Tuple[bool, str]:
    """Linux 右键菜单安装（Nautilus 脚本）"""
    scripts_dir = Path.home() / ".local/share/nautilus/scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    compress_script = scripts_dir / "FluxPack压缩"
    extract_script = scripts_dir / "FluxPack解压"

    compress_script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, os\n"
        f"sys.path.insert(0, '{Path(__file__).resolve().parent.parent.parent}')\n"
        "from pathlib import Path\n"
        "from src.core.formats import open_archive\n"
        "for arg in sys.argv[1:]:\n"
        "    p = Path(arg)\n"
        "    dst = p.parent / p.stem\n"
        "    dst.mkdir(parents=True, exist_ok=True)\n"
        "    try:\n"
        "        open_archive(p).extract(dst)\n"
        "        print(f'✅ {{p.name}} → {{dst}}')\n"
        "    except Exception as e:\n"
        "        print(f'❌ {{p.name}}: {{e}}')\n"
        "input('按 Enter 退出...')\n"
    )
    compress_script.chmod(0o755)

    # 压缩脚本
    extract_script.write_text(
        "#!/bin/bash\n"
        f"cd '{Path(__file__).resolve().parent.parent.parent}'\n"
        'exec python3 run_launcher.py gui "$@"\n'
    )
    extract_script.chmod(0o755)

    return True, f"已安装 Nautilus 脚本到 {scripts_dir}"


def _install_context_menu_windows() -> Tuple[bool, str]:
    """Windows 右键菜单安装（注册表）"""
    try:
        import winreg
    except ImportError:
        return False, "仅 Windows 支持右键菜单"

    installed = 0
    errors = []

    for item in SHELL_MENU_ITEMS:
        for base in item["extends"]:
            try:
                key_path = f"{base}\\{item['name']}"
                with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path) as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, item["display"])
                    if item.get("icon"):
                        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, item["icon"])

                # command subkey
                cmd_path = f"{key_path}\\command"
                with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, cmd_path) as key:
                    cmd = item["command"].replace("\\\"", "\"").replace("\\\\", "\\")
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, cmd)

                installed += 1
            except Exception as e:
                errors.append(f"{item['name']}@{base}: {e}")

    if installed > 0:
        return True, f"已安装 {installed} 个右键菜单项（需管理员权限）"
    return False, f"安装失败: {'; '.join(errors)}"


def uninstall_context_menu() -> Tuple[bool, str]:
    """卸载右键菜单"""
    if sys.platform == "win32":
        try:
            import winreg
        except ImportError:
            return False, "仅 Windows 支持"
        removed = 0
        for item in SHELL_MENU_ITEMS:
            for base in item["extends"]:
                try:
                    key_path = f"{base}\\{item['name']}"
                    try: winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, f"{key_path}\\command")
                    except: pass
                    try: winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, key_path)
                    except: pass
                    removed += 1
                except: pass
        return True, f"已移除 {removed} 个右键菜单项"
    elif sys.platform == "linux":
        scripts_dir = Path.home() / ".local/share/nautilus/scripts"
        removed = 0
        for f in ["FluxPack压缩", "FluxPack解压"]:
            p = scripts_dir / f
            if p.exists():
                p.unlink()
                removed += 1
        return True, f"已移除 {removed} 个 Nautilus 脚本"
    return False, f"不支持的平台: {sys.platform}"


def check_context_menu() -> List[Dict]:
    """检查右键菜单安装状态"""
    results = []
    try:
        import winreg
        for item in SHELL_MENU_ITEMS:
            for base in item["extends"]:
                key_path = f"{base}\\{item['name']}"
                try:
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key_path) as key:
                        display, _ = winreg.QueryValueEx(key, "")
                        results.append({
                            "name": item["display"],
                            "path": key_path,
                            "installed": True,
                            "display_text": display,
                        })
                except FileNotFoundError:
                    results.append({
                        "name": item["display"],
                        "path": key_path,
                        "installed": False,
                        "display_text": "",
                    })
    except ImportError:
        pass
    return results


# 上下文菜单回调（由注册表命令调用）
def _context_menu_compress(files: List[str]):
    """右键『压缩』回调"""
    from src.ui.desktop import FluxPackApp
    import customtkinter as ctk
    root = ctk.CTk()
    app = FluxPackApp()
    # 自动填入源文件并切换到压缩标签
    app.tabview.set("📦 压缩")
    app._cmp_sources = list(files)
    app._update_src_list()
    root.mainloop()


def _context_menu_extract(files: List[str]):
    """右键『解压』回调"""
    from src.core.formats import open_archive
    for f in files:
        p = Path(f)
        dst = p.parent / p.stem
        dst.mkdir(parents=True, exist_ok=True)
        try:
            archive = open_archive(p)
            archive.extract(dst)
            print(f"✅ 已解压到 {dst}")
        except Exception as e:
            print(f"❌ {p.name}: {e}")
    input("按 Enter 退出...")


def _context_menu_battle(files: List[str]):
    """右键『格式竞赛』回调"""
    results = format_battle([Path(f) for f in files])
    print("\n" + "=" * 60)
    print("🏆 压缩竞赛结果")
    print("=" * 60)
    for r in results:
        check = "🏆" if r.get("best") else "  "
        print(f"{check} {r['format']:<8} {r['size_fmt']:<10} {r['ratio']:>5.1f}%  {r['time']:.2f}s  {r['speed']:.1f} MB/s")
    print("=" * 60)
    if results:
        best = min(results, key=lambda x: x['ratio'])
        print(f"🏆 最佳格式: {best['format']} ({best['size_fmt']}, {best['ratio']:.1f}%)")
    input("\n按 Enter 退出...")


# ═══════════════════════════════════════════════════════════════════
# 2. 🏆 压缩竞赛 (Format Battle)
# ═══════════════════════════════════════════════════════════════════

def format_battle(sources: List[Path],
                  formats: Optional[List[str]] = None,
                  progress: Optional[Callable] = None) -> List[Dict]:
    """压缩竞赛——用多种格式压缩同一批文件，对比结果

    参数:
        sources: 源文件列表
        formats: 要测试的格式，默认全部
                 可用: zip, 7z, tar.gz, tar
        progress: 进度回调

    返回:
        [{format, size, ratio, time, speed, path}]
    """
    if formats is None:
        formats = ["zip", "7z", "tar.gz", "tar"]

    tmp = Path(tempfile.mkdtemp(prefix="flux_battle_"))
    results = []

    # 计算原始总大小
    total_raw = 0
    all_files = []
    for src in sources:
        if src.is_file():
            total_raw += src.stat().st_size
            all_files.append(src)
        elif src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    total_raw += f.stat().st_size
                    all_files.append(f)

    if not all_files:
        shutil.rmtree(tmp, ignore_errors=True)
        return []

    for fmt in formats:
        output = tmp / f"test.{fmt}"
        if progress:
            progress(f"测试 {fmt}...")

        start = time.time()
        try:
            if fmt == "zip":
                archive = ZipArchive(output)
            elif fmt == "7z":
                archive = SevenZipArchive(output)
            elif fmt == "tar.gz":
                archive = TarGzArchive(output.with_suffix(".tar.gz"))
                output = output.with_suffix(".tar.gz")
            elif fmt == "tar":
                archive = TarGzArchive(output.with_suffix(".tar"))
                output = output.with_suffix(".tar")
            else:
                continue

            archive.compress(all_files)
            elapsed = time.time() - start
            compressed_size = output.stat().st_size
            ratio = (compressed_size / total_raw * 100) if total_raw > 0 else 0
            speed = (total_raw / 1024 / 1024) / elapsed if elapsed > 0 else 0

            results.append({
                "format": fmt,
                "size": compressed_size,
                "size_fmt": _fmt_size(compressed_size),
                "ratio": ratio,
                "time": elapsed,
                "speed": speed,
                "path": str(output),
                "raw_size": total_raw,
            })
        except Exception as e:
            if progress:
                progress(f"  {fmt}: ❌ {e}")

    # 标记最佳（体积最小）
    if results:
        best = min(results, key=lambda x: x["ratio"])
        for r in results:
            r["best"] = (r["format"] == best["format"])

    shutil.rmtree(tmp, ignore_errors=True)
    return sorted(results, key=lambda x: x["ratio"])


# ═══════════════════════════════════════════════════════════════════
# 3. 🔓 批量密码解锁器
# ═══════════════════════════════════════════════════════════════════

def batch_password_unlock(archive_path: Path,
                          password_list: List[str],
                          output_dir: Optional[Path] = None,
                          auto_extract: bool = True,
                          progress: Optional[Callable] = None) -> Dict:
    """批量密码解锁——用密码列表尝试解锁压缩包

    参数:
        archive_path: 加密压缩包路径
        password_list: 密码列表（按优先级排序）
        output_dir: 解压输出目录
        auto_extract: 找到密码后自动解压
        progress: 进度回调 (attempt, total, current_pwd)

    返回:
        {found, password, attempts, elapsed, extracted_to}
    """
    result = {
        "found": False,
        "password": None,
        "attempts": 0,
        "elapsed": 0,
        "extracted_to": None,
    }

    if output_dir is None:
        output_dir = archive_path.parent / f"{archive_path.stem}_unlocked"

    start = time.time()
    total = len(password_list)

    for idx, pwd in enumerate(password_list):
        result["attempts"] = idx + 1

        if progress:
            progress(idx + 1, total, pwd)

        try:
            archive = open_archive(archive_path, password=pwd)
            entries = archive.list_contents()

            if len(entries) > 0:
                # 密码正确！
                result["found"] = True
                result["password"] = pwd
                result["elapsed"] = time.time() - start

                if auto_extract:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    archive.extract(output_dir)
                    result["extracted_to"] = str(output_dir)

                return result

        except ValueError:
            # 密码错误
            continue
        except Exception:
            # 其他错误—跳过
            continue

    result["elapsed"] = time.time() - start
    return result


def batch_unlock_from_file(archive_path: Path,
                           wordlist_path: Path,
                           output_dir: Optional[Path] = None,
                           auto_extract: bool = True,
                           progress: Optional[Callable] = None) -> Dict:
    """从字典文件批量解锁"""
    if not wordlist_path.exists():
        raise FileNotFoundError(f"字典文件不存在: {wordlist_path}")

    passwords = wordlist_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    passwords = [p.strip() for p in passwords if p.strip()]

    return batch_password_unlock(archive_path, passwords, output_dir, auto_extract, progress)


def unlock_with_smart_candidates(archive_path: Path,
                                 output_dir: Optional[Path] = None,
                                 auto_extract: bool = True,
                                 progress: Optional[Callable] = None) -> Dict:
    """使用智能密码候选列表解锁"""
    from .advanced import smart_password_candidates
    candidates = smart_password_candidates(archive_path)
    return batch_password_unlock(archive_path, candidates, output_dir, auto_extract, progress)


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def _fmt_size(size: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024: return f"{size:.1f} {u}" if u != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"
