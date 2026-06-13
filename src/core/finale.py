"""文件关联 / 拖拽压缩 / 预设 / 压缩模拟器"""

import os
import sys
import json
import time
import math
import random
import shutil
import tempfile
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Callable, Tuple
from dataclasses import dataclass, asdict

from .formats import open_archive, detect_format, ZipArchive, SevenZipArchive, TarGzArchive


HOME = Path.home() / ".fluxpack"
PROFILES_FILE = HOME / "profiles.json"


# ═══════════════════════════════════════════════════════════════════
# 1. 🖱 文件关联
# ═══════════════════════════════════════════════════════════════════

ARCHIVE_EXTS = [".7z", ".zip", ".rar", ".tar", ".gz", ".tar.gz"]


def register_file_associations() -> Tuple[bool, str]:
    """注册压缩包文件关联：双击用 FluxPack 打开"""
    try:
        import winreg
    except ImportError:
        return False, "仅 Windows 支持"

    exe_path = sys.executable
    if not exe_path.lower().endswith(".exe"):
        return False, "请从打包后的 EXE 运行"

    installed = 0
    errors = []

    for ext in ARCHIVE_EXTS:
        try:
            # ProgID
            prog_id = f"FluxPack.{ext[1:]}"
            # 创建 ProgID
            with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, prog_id) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"FluxPack 压缩包 (.{ext})")

            # DefaultIcon
            with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\DefaultIcon") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"{exe_path},0")

            # shell/open/command — 双击时打开 GUI 并加载该文件
            with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}" open "%1"')

            # 关联扩展名到 ProgID
            with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, ext) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, prog_id)

            installed += 1
        except Exception as e:
            errors.append(f"{ext}: {e}")

    if installed > 0:
        # 通知资源管理器刷新
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except:
            pass
        return True, f"已注册 {installed} 个扩展名关联（需管理员权限）"
    return False, f"注册失败: {'; '.join(errors)}"


def unregister_file_associations() -> Tuple[bool, str]:
    """卸载文件关联"""
    try:
        import winreg
    except ImportError:
        return False, "仅 Windows 支持"

    removed = 0
    for ext in ARCHIVE_EXTS:
        try:
            prog_id = f"FluxPack.{ext[1:]}"
            # 删除 ProgID
            try:
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command")
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open")
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell")
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\DefaultIcon")
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, prog_id)
            except: pass
            # 恢复默认关联
            try:
                winreg.DeleteKey(winreg.HKEY_CLASSES_ROOT, ext)
            except: pass
            removed += 1
        except: pass

    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except: pass

    return True, f"已移除 {removed} 个扩展名关联"


# ═══════════════════════════════════════════════════════════════════
# 2. 📥 拖拽快速压缩
# ═══════════════════════════════════════════════════════════════════

def quick_compress_dialog(files: List[str]) -> None:
    """拖拽文件到 EXE 时弹出压缩对话框"""
    from src.ui.desktop import FluxPackApp
    import customtkinter as ctk
    root = ctk.CTk()
    app = FluxPackApp()
    app.tabview.set("📦 压缩")
    app._cmp_sources = list(files)
    app._update_src_list()
    root.mainloop()


# ═══════════════════════════════════════════════════════════════════
# 3. 📋 压缩预设 (Profiles)
# ═══════════════════════════════════════════════════════════════════

DEFAULT_PROFILES = {
    "快速打包": {
        "format": "zip",
        "password": "",
        "volume": "",
        "hybrid": False,
        "level": "standard",
        "desc": "最快速度，兼容性最好",
    },
    "极限压缩": {
        "format": "7z",
        "password": "",
        "volume": "",
        "hybrid": True,
        "level": "maximum",
        "desc": "7z LZMA2 极限 + 混合算法",
    },
    "加密备份": {
        "format": "7z",
        "password": "",
        "volume": "",
        "hybrid": True,
        "level": "maximum",
        "desc": "AES-256 加密 + 极限压缩",
    },
    "邮件附件": {
        "format": "zip",
        "password": "",
        "volume": "25M",
        "hybrid": False,
        "level": "standard",
        "desc": "25MB ZIP 分卷，适合邮件",
    },
    "光盘刻录": {
        "format": "7z",
        "password": "",
        "volume": "700M",
        "hybrid": True,
        "level": "high",
        "desc": "700MB 分卷，CD-R 刻录",
    },
    "图片归档": {
        "format": "7z",
        "password": "",
        "volume": "",
        "hybrid": True,
        "level": "maximum",
        "desc": "图片优化 + 极限压缩",
    },
}


def load_profiles() -> Dict:
    """加载所有预设"""
    try:
        if PROFILES_FILE.exists():
            data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
            # 合并默认预设（用户自定义覆盖同名默认）
            merged = dict(DEFAULT_PROFILES)
            merged.update(data)
            return merged
    except Exception:
        pass
    return dict(DEFAULT_PROFILES)


def save_profile(name: str, profile: Dict) -> bool:
    """保存预设"""
    HOME.mkdir(parents=True, exist_ok=True)
    profiles = {}
    if PROFILES_FILE.exists():
        try:
            profiles = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except: pass
    profiles[name] = profile
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def delete_profile(name: str) -> bool:
    """删除预设"""
    if name in DEFAULT_PROFILES:
        return False  # 不能删除默认
    profiles = load_profiles()
    if name in profiles:
        del profiles[name]
        PROFILES_FILE.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    return False


def apply_profile(name: str, sources: List[Path], output: Path,
                  password: Optional[str] = None) -> Path:
    """应用预设进行压缩"""
    profiles = load_profiles()
    if name not in profiles:
        raise ValueError(f"预设不存在: {name}")

    p = profiles[name]
    pwd = password or p.get("password") or None
    vol = p.get("volume") or None
    hybrid = p.get("hybrid", False)
    fmt = p.get("format", "7z")

    out = output
    if not out.suffix:
        out = out.with_suffix(f".{fmt}")

    if hybrid and fmt == "7z":
        from .hybrid import hybrid_compress
        return hybrid_compress(sources, out, password=pwd)
    else:
        if fmt == "zip":
            archive = ZipArchive(out, password=pwd)
        elif fmt == "7z":
            archive = SevenZipArchive(out, password=pwd)
        elif fmt == "tar.gz":
            archive = TarGzArchive(out, password=pwd)
        else:
            archive = SevenZipArchive(out, password=pwd)
        archive.compress(sources, volume_size=_parse_vol(vol))
        return out


# ═══════════════════════════════════════════════════════════════════
# 4. 📊 压缩模拟器
# ═══════════════════════════════════════════════════════════════════

FORMATS_TO_SIMULATE = {
    "zip": {"label": "ZIP", "level": "standard"},
    "7z": {"label": "7Z", "level": "normal"},
    "7z_max": {"label": "7Z 极限", "level": "maximum"},
    "tar.gz": {"label": "TAR.GZ", "level": "standard"},
}


def simulate_compression(sources: List[Path],
                         sample_ratio: float = 0.05,
                         max_sample_size: int = 50 * 1024 * 1024,
                         progress: Optional[Callable] = None) -> Dict:
    """压缩模拟器：采样压缩估计最终结果

    参数:
        sources: 源文件列表
        sample_ratio: 采样比例 (0~1)
        max_sample_size: 最大采样大小（字节）

    返回:
        {格式: {estimated_size, estimated_ratio, estimated_time, speed, ...}}
    """
    # 收集所有文件信息
    all_files = []
    total_size = 0
    for src in sources:
        if src.is_file():
            all_files.append(src)
            total_size += src.stat().st_size
        elif src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    all_files.append(f)
                    total_size += f.stat().st_size

    if not all_files:
        return {}

    # 采样
    random.shuffle(all_files)
    sample_max = max(1, int(len(all_files) * sample_ratio))
    sample_size = 0
    sampled = []
    for f in all_files:
        if len(sampled) >= sample_max:
            break
        if sample_size + f.stat().st_size > max_sample_size:
            continue
        sampled.append(f)
        sample_size += f.stat().st_size

    if not sampled:
        sampled = [all_files[0]]

    if progress:
        progress(f"采样 {len(sampled)} 个文件 ({_fmt_size(sample_size)})")

    # 用每种格式压缩采样文件
    results = {}
    tmp_dir = Path(tempfile.mkdtemp(prefix="flux_sim_"))

    try:
        for fmt, info in FORMATS_TO_SIMULATE.items():
            if progress:
                progress(f"测试 {info['label']}...")

            out = tmp_dir / f"sample.{'7z' if '7z' in fmt else fmt}"

            start = time.time()
            try:
                if fmt == "zip":
                    ZipArchive(out).compress(sampled)
                elif fmt == "7z":
                    SevenZipArchive(out).compress(sampled)
                elif fmt == "7z_max":
                    import py7zr
                    filters_list = [{"id": py7zr.FILTER_LZMA2}]
                    try:
                        with py7zr.SevenZipFile(out, "w", filters=filters_list) as szf:
                            for f in sampled:
                                szf.write(f, f.name)
                    except Exception:
                        # 降级到无filter
                        with py7zr.SevenZipFile(out, "w") as szf:
                            for f in sampled:
                                szf.write(f, f.name)
                elif fmt == "tar.gz":
                    TarGzArchive(out).compress(sampled)

                elapsed = time.time() - start
                comp_size = out.stat().st_size
                ratio = (comp_size / sample_size * 100) if sample_size > 0 else 0
                speed = (sample_size / 1024 / 1024) / elapsed if elapsed > 0 else 0

                # 估算总压缩结果
                est_size = total_size * ratio / 100
                est_time = total_size / (speed * 1024 * 1024) if speed > 0 else 0

                results[fmt] = {
                    "label": info["label"],
                    "sample_size": sample_size,
                    "compressed_size": comp_size,
                    "ratio": ratio,
                    "speed_mbps": speed,
                    "sample_time": elapsed,
                    "estimated_size": est_size,
                    "estimated_size_fmt": _fmt_size(est_size),
                    "estimated_ratio": ratio,
                    "estimated_time": est_time,
                    "estimated_time_fmt": _fmt_time(est_time),
                }
            except Exception as e:
                results[fmt] = {"label": info["label"], "error": str(e)}

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    results["_meta"] = {
        "total_size": total_size,
        "total_size_fmt": _fmt_size(total_size),
        "total_files": len(all_files),
        "sampled_files": len(sampled),
        "sample_ratio": sample_ratio,
    }

    return results


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def _fmt_size(size: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024: return f"{size:.1f} {u}" if u != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"


def _fmt_time(seconds: float) -> str:
    if seconds < 60: return f"{seconds:.0f}s"
    if seconds < 3600: return f"{seconds//60:.0f}m {seconds%60:.0f}s"
    return f"{seconds//3600:.0f}h {seconds%3600//60:.0f}m"


def _parse_vol(s):
    if not s: return None
    s = str(s).upper().strip()
    if s.endswith("G"): return int(float(s[:-1]) * 1024**3)
    if s.endswith("M"): return int(float(s[:-1]) * 1024**2)
    if s.endswith("K"): return int(float(s[:-1]) * 1024)
    try: return int(s)
    except: return None
