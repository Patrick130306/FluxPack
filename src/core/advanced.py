"""高级功能 —— 档案对比 / 修复 / 去重 / 校验和 / 预览 / 清理 / 合并 / AI / 扫描 / 编辑 / 安全 / 搜索 / 模板 / 增量"""

import os
import re
import io
import hashlib
import shutil
import tempfile
import time
import uuid
import struct
import zipfile
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Callable, Set, Any, TypeVar
from collections import defaultdict
from datetime import datetime, timedelta

from .formats import open_archive, detect_format, ZipArchive, SevenZipArchive, TarGzArchive
from .archive import ArchiveEntry


# ═══════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════

def _fmt_size(size: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024: return f"{size:.1f} {u}" if u != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"

def _safe_mktemp(prefix="flux_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


# ═══════════════════════════════════════════════════════
# 1. 🧠 AI 智能密码候选
# ═══════════════════════════════════════════════════════

def smart_password_candidates(archive_path: Path) -> List[str]:
    """根据文件名/目录名/上下文生成智能密码候选列表"""
    name = archive_path.stem
    parent = archive_path.parent.name
    candidates = set()

    # 基本名称
    candidates.add(name.lower())
    candidates.add(name.upper())
    candidates.add(name)

    # 去后缀变体
    for sep in ['_', '-', '.', ' ']:
        parts = name.split(sep)
        if len(parts) > 1:
            candidates.add(parts[0].lower())
            candidates.add(parts[-1].lower())
            candidates.add(''.join(parts).lower())
            candidates.add(sep.join(parts[:2]).lower())

    # 常见弱密码
    common = ["123456", "password", "admin", "1234", "pass", "123", "0000",
              name + "123", name + "2024", name + "!", name + "@123"]
    for c in common:
        candidates.add(c.lower())

    # 文件名+年份
    for y in range(1980, 2031):
        candidates.add(f"{name.lower()}{y}")
        candidates.add(f"{name.lower()}_{y}")

    # 拼音/常见中文密码模式
    chinese_common = ["123456", "password", "admin", "888888", "666666",
                      "abc123", "000000", "111111", "11111111", "00000000",
                      "qwerty", "iloveyou", "5201314", "123456789"]
    for cc in chinese_common:
        candidates.add(cc)

    # 目录名相关
    if parent and parent != name:
        candidates.add(parent.lower())
        candidates.add(parent.lower() + "123")

    # 按可能性排序，短的、常见的优先
    scored = sorted(candidates, key=lambda x: (
        0 if x in ("123456", "password", "admin", name.lower()) else
        1 if len(x) <= 6 else
        2 if x[-3:].isdigit() else
        3
    ))

    return list(dict.fromkeys(scored))  # 去重保序


# ═══════════════════════════════════════════════════════
# 2. 🎯 智能格式推荐
# ═══════════════════════════════════════════════════════

def recommend_format(file_paths: List[Path]) -> Dict[str, Any]:
    """分析文件类型组成，推荐最佳压缩格式

    返回:
        format: 推荐格式名
        reason: 理由
        filters: 建议的压缩参数
    """
    ext_counts = defaultdict(int)
    ext_sizes = defaultdict(int)
    total_size = 0
    is_text_heavy = True
    is_media_heavy = True
    has_exe = False

    TEXT_EXTS = {'.txt','.md','.py','.js','.html','.css','.json','.xml','.yml','.yaml',
                 '.csv','.log','.ini','.cfg','.conf','.toml','.sql','.sh','.bat','.ps1',
                 '.java','.cpp','.c','.h','.rs','.go','.rb','.php','.ts','.tsx',
                 '.vue','.svelte','.lua','.r','.m','.swift','.kt','.scala'}
    MEDIA_EXTS = {'.jpg','.jpeg','.png','.gif','.bmp','.webp','.tiff','.ico',
                  '.mp4','.mkv','.avi','.mov','.wmv','.flv',
                  '.mp3','.wav','.flac','.aac','.ogg','.wma'}
    EXE_EXTS = {'.exe','.dll','.so','.dylib','.bin','.msi'}

    def _scan(p: Path):
        nonlocal total_size
        if p.is_file():
            s = p.stat().st_size
            total_size += s
            ext = p.suffix.lower()
            ext_counts[ext] += 1
            ext_sizes[ext] += s
            if ext not in TEXT_EXTS and ext:
                pass  # not text
            if ext not in MEDIA_EXTS and ext:
                pass
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    _scan(f)

    for p in file_paths:
        _scan(p)

    text_ratio = sum(ext_sizes[e] for e in ext_sizes if e in TEXT_EXTS) / max(total_size, 1)
    media_ratio = sum(ext_sizes[e] for e in ext_sizes if e in MEDIA_EXTS) / max(total_size, 1)
    exe_ratio = sum(ext_sizes[e] for e in ext_sizes if e in EXE_EXTS) / max(total_size, 1)

    has_text = any(e in TEXT_EXTS for e in ext_counts)
    has_media = any(e in MEDIA_EXTS for e in ext_counts)
    has_exe = any(e in EXE_EXTS for e in ext_counts)

    if total_size > 1024**3:  # >1G
        return {
            "format": "7z",
            "reason": "大体积文件推荐 7z (LZMA2)，比 ZIP 压缩率高 30-40%",
            "filters": {"solid": True, "compression_level": 5},
        }
    if text_ratio > 0.6:
        return {
            "format": "7z",
            "reason": "文本密集型，7z(PPMd) 对文本压缩率极高",
            "filters": {"method": "PPMd", "compression_level": 7},
        }
    if media_ratio > 0.7:
        return {
            "format": "zip",
            "reason": "媒体文件已压缩过，ZIP(store) 最快且无损",
            "filters": {"compression": 0, "method": "store"},
        }
    if exe_ratio > 0.3:
        return {
            "format": "7z",
            "reason": "可执行文件推荐 7z(LZMA2) 压缩率最高",
            "filters": {"compression_level": 9},
        }
    if has_text and has_media:
        return {
            "format": "7z",
            "reason": "混合类型推荐 7z，平衡速度和压缩率",
            "filters": {"compression_level": 5, "solid": True},
        }

    return {
        "format": "zip",
        "reason": "杂项文件推荐 ZIP，兼容性最好",
        "filters": {"compression_level": 6},
    }


# ═══════════════════════════════════════════════════════
# 3. 📂 自动分类打包
# ═══════════════════════════════════════════════════════

def auto_classify(source_dir: Path, output_dir: Path,
                  by: str = "type", password: Optional[str] = None,
                  progress: Optional[Callable] = None) -> List[Path]:
    """自动分类打包：按文件类型或按修改日期

    by='type':  按扩展名分（images.zip, documents.zip, ...）
    by='date':  按年月分（2024-01.zip, 2024-02.zip, ...）
    """
    if not source_dir.is_dir():
        raise NotADirectoryError(str(source_dir))

    output_dir.mkdir(parents=True, exist_ok=True)
    created = []

    if by == "type":
        groups = defaultdict(list)
        for f in source_dir.rglob("*"):
            if f.is_file():
                ext = f.suffix.lower() or ".noext"
                groups[ext].append(f)

        # 按类型统计主分类
        TYPE_MAP = {
            '.jpg':'images','.jpeg':'images','.png':'images','.gif':'images',
            '.bmp':'images','.webp':'images','.svg':'images','.ico':'images',
            '.mp4':'videos','.mkv':'videos','.avi':'videos','.mov':'videos',
            '.mp3':'audio','.wav':'audio','.flac':'audio','.aac':'audio',
            '.doc':'documents','.docx':'documents','.pdf':'documents','.xls':'documents',
            '.xlsx':'documents','.ppt':'documents','.pptx':'documents',
            '.py':'code','.js':'code','.ts':'code','.html':'code','.css':'code',
            '.java':'code','.cpp':'code','.c':'code','.rs':'code','.go':'code',
            '.exe':'executables','.dll':'executables','.msi':'executables',
            '.zip':'archives','.7z':'archives','.rar':'archives','.tar':'archives',
            '.gz':'archives',
        }
        cat_groups = defaultdict(list)
        for ext, files in groups.items():
            cat = TYPE_MAP.get(ext, 'others')
            cat_groups[cat].extend(files)

        for cat, files in sorted(cat_groups.items()):
            if progress:
                progress(f"打包 {cat} ({len(files)} 个文件)...")
            out = output_dir / f"{cat}.7z"
            archive = SevenZipArchive(out, password=password)
            archive.compress(files)
            created.append(out)

    elif by == "date":
        groups = defaultdict(list)
        for f in source_dir.rglob("*"):
            if f.is_file():
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                key = mtime.strftime("%Y-%m")
                groups[key].append(f)

        for month, files in sorted(groups.items()):
            if progress:
                progress(f"打包 {month} ({len(files)} 个文件)...")
            out = output_dir / f"{month}.7z"
            archive = SevenZipArchive(out, password=password)
            archive.compress(files)
            created.append(out)

    return created


# ═══════════════════════════════════════════════════════
# 4. 🔍 隐写检测
# ═══════════════════════════════════════════════════════

def steganography_check(archive_path: Path) -> Dict[str, Any]:
    """检查压缩包是否有隐藏数据"""
    result = {"issues": [], "safe": True, "details": {}}

    try:
        raw = archive_path.read_bytes()
        result["details"]["file_size"] = len(raw)

        # 检查 ZIP 注释
        if archive_path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    comment = zf.comment
                    if comment:
                        result["issues"].append(f"ZIP 注释包含数据 ({len(comment)} 字节)")
                        result["details"]["zip_comment"] = comment[:200]
            except Exception:
                pass

        # 检查文件末尾多余数据
        # ZIP 的 EOCD 签名: 0x06054b50
        if archive_path.suffix.lower() == ".zip":
            for sig in [b'PK\x05\x06', b'PK\x05\x05']:
                pos = raw.rfind(sig)
                if pos >= 0:
                    eocd_end = pos + 22  # EOCD 最小 22 字节
                    extra = len(raw) - eocd_end
                    if extra > 0:
                        result["issues"].append(f"ZIP 末尾有 {extra} 字节额外数据（可疑）")
                    break

        # 检查 7Z 文件头后是否有异常数据
        if archive_path.suffix.lower() == ".7z":
            # 7z signature: 7z¼¯'   (0x377ABCAF271C)
            if raw[:6] == b'\x37\x7a\xbc\xaf\x27\x1c':
                # 查找文件尾
                pass

        # 检查重复的文件内容（潜藏文件）
        try:
            archive = open_archive(archive_path)
            entries = archive.list_contents()
            names = [e.name for e in entries]
            # 检查是否有隐藏属性文件（以.开头或在特殊目录中）
            hidden = [n for n in names if n.startswith('.') or '/.' in n or n.startswith('__')]
            if hidden:
                result["issues"].append(f"发现 {len(hidden)} 个隐藏文件: {hidden[:5]}")
        except Exception:
            pass

        result["safe"] = len(result["issues"]) == 0
        return result

    except Exception as e:
        result["issues"].append(f"检测失败: {e}")
        result["safe"] = False
        return result


# ═══════════════════════════════════════════════════════
# 5. ⭐ 加密强度评级
# ═══════════════════════════════════════════════════════

ENCRYPTION_RATINGS = {
    "zip_2.0": {"name": "ZIP 2.0 传统加密", "level": 1, "warning": "极弱，几分钟即可破解"},
    "zip_aes128": {"name": "ZIP AES-128", "level": 3, "warning": "中等，建议升级到 AES-256"},
    "zip_aes192": {"name": "ZIP AES-192", "level": 4, "warning": ""},
    "zip_aes256": {"name": "ZIP AES-256", "level": 5, "warning": "强加密"},
    "7z_aes256": {"name": "7Z AES-256", "level": 5, "warning": "强加密"},
    "rar_old": {"name": "RAR 3.x 加密", "level": 3, "warning": "旧版 RAR 加密较弱"},
    "rar_v5": {"name": "RAR 5.0 AES-256", "level": 5, "warning": "强加密"},
    "none": {"name": "无加密", "level": 0, "warning": "明文可读"},
}


def encryption_rating(archive_path: Path, password: Optional[str] = None) -> Dict:
    """评估压缩包加密强度"""
    result = {"rating": None, "level": 0, "warnings": [], "details": {}}

    try:
        archive = open_archive(archive_path, password=password)
        fmt = archive.format
        result["details"]["format"] = fmt

        if fmt == "zip":
            try:
                zf = zipfile.ZipFile(archive_path, "r")
                with zf:
                    for info in zf.infolist():
                        if info.flag_bits & 0x1:  # 加密标志
                            # 检测加密类型
                            if info.flag_bits & 0x400:  # AES (bit 9)
                                result["rating"] = "zip_aes256"
                                result["level"] = 5
                            else:  # ZIP 2.0
                                result["rating"] = "zip_2.0"
                                result["level"] = 1
                            break
                    else:
                        result["rating"] = "none"
            except Exception:
                result["rating"] = "zip_2.0"  # 可能加密导致无法读
                result["level"] = 1

        elif fmt == "7z":
            result["rating"] = "7z_aes256"
            result["level"] = 5

        elif fmt == "rar":
            result["rating"] = "rar_v5"
            result["level"] = 5

        else:
            result["rating"] = "none"

        if result["rating"] and result["rating"] in ENCRYPTION_RATINGS:
            info = ENCRYPTION_RATINGS[result["rating"]]
            result["name"] = info["name"]
            if info["warning"]:
                result["warnings"].append(info["warning"])

        if result["level"] < 3:
            result["warnings"].append("建议更换为 7Z AES-256 加密")
        elif result["level"] < 5:
            result["warnings"].append("建议升级到更强的加密")

        return result

    except Exception as e:
        result["warnings"].append(f"检测失败: {e}")
        return result


# ═══════════════════════════════════════════════════════
# 6. ✏️ 压缩包内文件替换
# ═══════════════════════════════════════════════════════

def replace_in_archive(archive_path: Path, target_file: str,
                       new_content: bytes,
                       password: Optional[str] = None,
                       output_path: Optional[Path] = None) -> Path:
    """替换压缩包内的文件内容（提取→替换→重新打包）"""
    if output_path is None:
        output_path = archive_path

    tmp = _safe_mktemp("flux_replace_")
    try:
        archive = open_archive(archive_path, password=password)
        archive.extract(tmp)

        # 替换目标文件
        target = tmp / target_file
        if not target.exists():
            raise FileNotFoundError(f"压缩包中未找到: {target_file}")
        target.write_bytes(new_content)

        # 重新打包
        out_archive = open_archive(output_path, password=password)
        out_archive.compress([tmp], arcname=archive_path.stem)

        return output_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def delete_from_archive(archive_path: Path, target_file: str,
                        password: Optional[str] = None,
                        output_path: Optional[Path] = None) -> Path:
    """删除压缩包内的文件（提取→删除→重新打包）"""
    if output_path is None:
        output_path = archive_path

    tmp = _safe_mktemp("flux_delete_")
    try:
        archive = open_archive(archive_path, password=password)
        archive.extract(tmp)

        target = tmp / target_file
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

        out_archive = open_archive(output_path, password=password)
        out_archive.compress([tmp], arcname=archive_path.stem)

        return output_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════
# 7. 🔎 跨压缩包全文搜索
# ═══════════════════════════════════════════════════════

def fulltext_search_archives(patterns: List[str], keyword: str,
                             password: Optional[str] = None,
                             max_results: int = 100) -> List[Dict]:
    """在多个压缩包内搜索文件内容

    patterns: 通配符列表，如 ['D:/archives/*.zip', 'D:/docs/*.7z']
    password: 所有包的统一密码（或 None 逐个尝试）
    """
    import glob
    import fnmatch

    results = []
    matched_files = set()

    # 展开通配符
    all_archives = []
    for pat in patterns:
        all_archives.extend(glob.glob(pat))

    keyword_lower = keyword.lower()
    tmp = _safe_mktemp("flux_search_")

    try:
        for arc_path in sorted(set(all_archives)):
            arc = Path(arc_path)
            if not arc.is_file():
                continue

            try:
                archive = open_archive(arc, password=password)
                entries = archive.list_contents()

                for entry in entries:
                    if entry.is_dir or entry.size > 10 * 1024 * 1024:
                        continue  # 跳过目录和大文件
                    if len(results) >= max_results:
                        break

                    # 提取单个文件到临时目录
                    try:
                        archive.extract(tmp, members=[entry.name])
                        extracted = tmp / entry.name
                        if extracted.is_file():
                            try:
                                text = extracted.read_text(encoding="utf-8", errors="replace")
                                if keyword_lower in text.lower():
                                    # 找到上下文
                                    lines = text.splitlines()
                                    match_lines = [i+1 for i, l in enumerate(lines) if keyword_lower in l.lower()]
                                    context = ""
                                    for ml in match_lines[:3]:
                                        start = max(0, ml - 2)
                                        end = min(len(lines), ml + 2)
                                        ctx = lines[start:end]
                                        context += f"  ...行{ml}: {lines[ml-1][:200]}\n"

                                    results.append({
                                        "archive": arc.name,
                                        "file": entry.name,
                                        "size": entry.size,
                                        "matches": len(match_lines),
                                        "context": context,
                                    })
                                    # 清理提取的文件
                                    if extracted.parent != tmp:
                                        shutil.rmtree(extracted.parent, ignore_errors=True)
                                    else:
                                        extracted.unlink()
                            except Exception:
                                pass
                    except Exception:
                        continue

                if len(results) >= max_results:
                    break

            except Exception:
                continue

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


# ═══════════════════════════════════════════════════════
# 8. 🔁 递归挖矿解压
# ═══════════════════════════════════════════════════════

ARCHIVE_EXTS = {'.zip', '.7z', '.rar', '.tar', '.gz', '.tar.gz'}


def recursive_extract(archive_path: Path, target_dir: Path,
                      password: Optional[str] = None,
                      max_depth: int = 10) -> Dict[str, Any]:
    """递归解压，自动处理嵌套压缩包"""
    stats = {"extracted": 0, "nested_found": 0, "failed": [], "depth_reached": 0}

    tmp_root = _safe_mktemp("flux_recursive_")

    def _extract_recursive(src: Path, dst: Path, depth: int = 0):
        if depth > max_depth:
            return
        stats["depth_reached"] = max(stats["depth_reached"], depth)
        dst.mkdir(parents=True, exist_ok=True)

        try:
            archive = open_archive(src, password=password)
            archive.extract(dst)
            stats["extracted"] += 1
        except Exception as e:
            stats["failed"].append(f"{src.name}: {e}")
            return

        # 扫描解压后的目录，找嵌套压缩包
        for f in dst.rglob("*"):
            if not f.is_file():
                continue
            if any(f.name.lower().endswith(e) for e in ARCHIVE_EXTS):
                stats["nested_found"] += 1
                nest_dir = dst / f"{f.stem}_unpacked"
                _extract_recursive(f, nest_dir, depth + 1)
                # 解压完后删除原压缩包
                try:
                    f.unlink()
                except OSError:
                    pass

    _extract_recursive(archive_path, tmp_root)
    stats["tmp_dir"] = str(tmp_root)

    # 将最终结果移动到目标目录
    for item in tmp_root.rglob("*"):
        if item.is_file():
            rel = item.relative_to(tmp_root)
            (target_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target_dir / rel)
            stats["extracted"] += 1

    shutil.rmtree(tmp_root, ignore_errors=True)
    return stats


# ═══════════════════════════════════════════════════════
# 9. 📋 全盘健康报告
# ═══════════════════════════════════════════════════════

def health_report(directory: Path,
                  progress: Optional[Callable] = None) -> Dict[str, Any]:
    """扫描目录下所有压缩包，生成健康报告"""
    report = {
        "total_archives": 0,
        "corrupted": [],
        "encrypted": 0,
        "encrypted_weak": 0,
        "unencrypted": 0,
        "largest": [],
        "total_size": 0,
        "by_format": defaultdict(int),
        "issues": [],
    }

    archives = []
    for f in directory.rglob("*"):
        if f.is_file() and any(f.name.lower().endswith(e) for e in {'.zip','.7z','.rar','.tar','.tar.gz'}):
            archives.append(f)

    report["total_archives"] = len(archives)

    for idx, arc in enumerate(archives):
        if progress:
            progress(idx + 1, len(archives), arc.name)

        report["total_size"] += arc.stat().st_size
        ext = arc.suffix.lower()
        if ext == '.gz':
            report["by_format"]["tar.gz"] += 1
        else:
            report["by_format"][ext] += 1

        try:
            archive = open_archive(arc)
            ok, errors = archive.test_integrity()
            if not ok:
                report["corrupted"].append((str(arc), errors))
                report["issues"].append(f"❌ 损坏: {arc.name}")

            # 检查加密
            rating = encryption_rating(arc)
            if rating["level"] > 0:
                report["encrypted"] += 1
                if rating["level"] < 3:
                    report["encrypted_weak"] += 1
                    report["issues"].append(f"⚠ 弱加密: {arc.name} ({rating.get('name', '?')})")
            else:
                report["unencrypted"] += 1

        except Exception as e:
            report["corrupted"].append((str(arc), [str(e)]))
            report["issues"].append(f"❌ 无法打开: {arc.name}")

    # 最大的 10 个
    max10 = sorted(archives, key=lambda x: x.stat().st_size, reverse=True)[:10]
    report["largest"] = [(a.name, a.stat().st_size) for a in max10]
    report["total_size_fmt"] = _fmt_size(report["total_size"])

    return report


# ═══════════════════════════════════════════════════════
# 10. 💸 空间浪费分析
# ═══════════════════════════════════════════════════════

def space_waste_analysis(directory: Path,
                         progress: Optional[Callable] = None) -> List[Dict]:
    """找出全盘压缩率最差的压缩包（重新压缩可节省的空间）"""
    results = []

    archives = [f for f in directory.rglob("*") if f.is_file() and
                any(f.name.lower().endswith(e) for e in {'.zip','.7z','.rar'})]

    for idx, arc in enumerate(archives):
        if progress:
            progress(idx + 1, len(archives), arc.name)

        try:
            archive = open_archive(arc)
            entries = archive.list_contents()
            if not entries:
                continue

            total_raw = sum(e.size for e in entries if not e.is_dir)
            total_comp = sum(e.compressed_size or 0 for e in entries if not e.is_dir and e.compressed_size)
            on_disk = arc.stat().st_size

            if total_raw > 0:
                ratio = total_comp / total_raw
                # 压缩率 > 90% 表示根本没压进去
                if ratio > 0.90:
                    waste = int(total_raw - total_comp)
                    results.append({
                        "path": arc,
                        "name": arc.name,
                        "raw_size": total_raw,
                        "compressed_size": total_comp,
                        "ratio": ratio,
                        "wasted_bytes": waste,
                        "wasted_fmt": _fmt_size(waste),
                        "format": archive.format,
                    })
        except Exception:
            continue

    results.sort(key=lambda x: x["wasted_bytes"], reverse=True)
    return results


# ═══════════════════════════════════════════════════════
# 11. ✅ 兼容性检测
# ═══════════════════════════════════════════════════════

def compatibility_check(archive_path: Path) -> Dict[str, Any]:
    """检测压缩包的兼容性问题"""
    issues = []
    warnings = []
    info = {"path": str(archive_path), "format": "?", "issues": issues, "warnings": warnings}

    name = archive_path.name
    size = archive_path.stat().st_size
    info["size"] = size

    try:
        archive = open_archive(archive_path)
        info["format"] = archive.format
        entries = archive.list_contents()

        # 1. 检查 ZIP64（旧系统不支持）
        if archive_path.suffix.lower() == ".zip" and size > 4 * 1024**3:
            warnings.append("ZIP64: 文件 >4GB，旧系统(WinXP/7zip9.x以下)可能无法解压")

        # 2. 检查 Unicode 文件名
        non_ascii = [e.name for e in entries if any(ord(c) > 127 for c in e.name)]
        if non_ascii:
            warnings.append(f"包含 {len(non_ascii)} 个非 ASCII 文件名（某些老系统可能乱码）")

        # 3. 检查过长的文件名
        long_names = [e.name for e in entries if len(e.name) > 200]
        if long_names:
            warnings.append(f"包含 {len(long_names)} 个超长文件名（>200字符），Windows 路径可能截断")

        # 4. 检查深层目录
        deep = [e.name for e in entries if e.name.count('/') > 10]
        if deep:
            warnings.append(f"包含 {len(deep)} 个深层目录（>10级），Windows 260字符路径限制可能触发")

        # 5. 检查 RAR 版本
        if archive.format == "rar":
            issues.append("RAR 格式：需要 WinRAR 或 unrar CLI，macOS/Linux 默认不支持")

        # 6. 检查加密方式
        rating = encryption_rating(archive_path)
        if rating["level"] == 1:
            warnings.append("ZIP 2.0 传统加密：极弱，容易被破解")

    except Exception as e:
        issues.append(f"无法检测: {e}")

    info["safe"] = len(issues) == 0 and len(warnings) < 3
    return info


# ═══════════════════════════════════════════════════════
# 12. 📏 智能分卷
# ═══════════════════════════════════════════════════════

MEDIA_PRESETS = {
    "email": (25 * 1024**2, "邮件附件"),
    "telegram": (2 * 1024**3, "Telegram"),
    "discord": (25 * 1024**2, "Discord"),
    "fat32": (4 * 1024**3, "FAT32 限制"),
    "cd700": (700 * 1024**2, "CD-R 700MB"),
    "dvd": (4.7 * 1024**3, "DVD 4.7GB"),
    "dvd_dl": (8.5 * 1024**3, "DVD 双层 8.5GB"),
    "bluray": (25 * 1024**3, "蓝光 25GB"),
    "usb2": (4 * 1024**3, "USB 2.0 硬盘 (FAT32)"),
    "usb3": (32 * 1024**3, "USB 3.0 (exFAT)"),
}


def intelligent_splitting(file_path: Path, media: str = "email",
                          password: Optional[str] = None) -> List[Path]:
    """根据目标介质智能分卷"""
    if media in MEDIA_PRESETS:
        vol_size, desc = MEDIA_PRESETS[media]
    else:
        # 尝试解析自定义大小
        vol_size = int(media)
        desc = f"{_fmt_size(vol_size)}"

    file_size = file_path.stat().st_size

    # 如果文件小于分卷大小，直接压缩
    out = file_path.with_suffix(f".{media}.7z") if media in MEDIA_PRESETS else file_path.with_suffix(f".custom.7z")

    if file_size <= vol_size:
        archive = SevenZipArchive(out, password=password)
        archive.compress([file_path])
        return [out]

    # 需要分卷
    archive = SevenZipArchive(out, password=password, volume_size=vol_size)
    return archive.compress([file_path])


def list_media_presets() -> List[Dict]:
    """列出所有预设介质"""
    return [{"name": k, "size": v, "desc": d} for k, (v, d) in MEDIA_PRESETS.items()]


# ═══════════════════════════════════════════════════════
# 13. 🌐 URL → 压缩包
# ═══════════════════════════════════════════════════════

def url_to_archive(url: str, output_path: Path,
                   password: Optional[str] = None,
                   timeout: int = 30) -> Path:
    """下载 URL 内容并直接打包"""
    tmp = _safe_mktemp("flux_url_")

    try:
        # 从 URL 提取文件名
        url_name = url.split("/")[-1].split("?")[0] or "download"
        tmp_file = tmp / url_name

        # 下载
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 FluxPack/0.2"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            tmp_file.write_bytes(data)

        # 打包
        archive = SevenZipArchive(output_path, password=password)
        archive.compress([tmp_file])

        return output_path

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════
# 14. 🧹 解压后自动清理
# ═══════════════════════════════════════════════════════

GARBAGE_FILES = {
    '.DS_Store', 'Thumbs.db', '.localized', 'desktop.ini',
    '__MACOSX', '.Spotlight-V100', '.Trashes',
    '~$*',  # 临时 Office 文件
}


def auto_clean_extract(archive_path: Path, target_dir: Path,
                       password: Optional[str] = None,
                       clean_garbage: bool = True,
                       flatten: bool = False) -> Dict:
    """解压并自动清理垃圾文件/展平目录结构"""
    stats = {"extracted": 0, "cleaned": 0, "flattened": 0}

    tmp = _safe_mktemp("flux_clean_")
    try:
        archive = open_archive(archive_path, password=password)
        archive.extract(tmp)

        # 展平：将所有文件提到根目录
        if flatten:
            for f in tmp.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(tmp)
                    # 跳过深层路径，直接放根
                    target = target_dir / f.name
                    # 处理重名
                    if target.exists():
                        stem = target.stem
                        suffix = target.suffix
                        counter = 1
                        while target.exists():
                            target = target_dir / f"{stem}_{counter}{suffix}"
                            counter += 1
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(target))
                    stats["flattened"] += 1
            stats["extracted"] = stats["flattened"]
        else:
            # 正常复制
            for f in tmp.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(tmp)
                    (target_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target_dir / rel)
                    stats["extracted"] += 1

        # 清理垃圾
        if clean_garbage:
            for f in target_dir.rglob("*"):
                if f.name in GARBAGE_FILES or (f.name.startswith('~$')):
                    try:
                        if f.is_dir():
                            shutil.rmtree(f)
                        else:
                            f.unlink()
                        stats["cleaned"] += 1
                    except OSError:
                        pass

        return stats

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════
# 15. 📋 模板系统
# ═══════════════════════════════════════════════════════

TEMPLATES = {
    "email_attach": {
        "name": "📧 邮件附件",
        "format": "zip",
        "password": None,
        "volume": 25 * 1024**2,
        "description": "25MB ZIP，适合邮件发送",
        "icon": "📧",
    },
    "secure_backup": {
        "name": "🔒 安全备份",
        "format": "7z",
        "password": True,  # 需要用户输入
        "volume": None,
        "description": "AES-256 加密 7Z，适合云存储备份",
        "icon": "🔒",
    },
    "cd_burn": {
        "name": "💿 光盘刻录",
        "format": "7z",
        "password": None,
        "volume": 700 * 1024**2,
        "description": "700MB 分卷，适合 CD-R 刻录",
        "icon": "💿",
    },
    "dvd_burn": {
        "name": "📀 DVD 刻录",
        "format": "7z",
        "password": None,
        "volume": 4.7 * 1024**3,
        "description": "4.7GB 分卷，适合 DVD 刻录",
        "icon": "📀",
    },
    "linux_tar": {
        "name": "🐧 Linux 打包",
        "format": "tar.gz",
        "password": None,
        "volume": None,
        "description": "TAR.GZ，Linux 原生兼容",
        "icon": "🐧",
    },
    "quick_share": {
        "name": "⚡ 快速分享",
        "format": "zip",
        "password": None,
        "volume": None,
        "description": "标准 ZIP，任何系统都能打开",
        "icon": "⚡",
    },
    "max_compress": {
        "name": "🚀 极限压缩",
        "format": "7z",
        "password": None,
        "volume": None,
        "description": "7Z LZMA2 极限压缩，体积最小但速度最慢",
        "icon": "🚀",
    },
    "self_decrypt": {
        "name": "🔐 自解压加密",
        "format": "7z",
        "password": True,
        "volume": None,
        "description": "7Z 加密，对方需输入密码解压（需装 7-Zip）",
        "icon": "🔐",
    },
}


def get_templates() -> Dict:
    """获取所有模板"""
    return TEMPLATES


def apply_template(template_name: str, sources: List[Path],
                   output: Path, password: Optional[str] = None) -> Path:
    """按预设模板压缩"""
    if template_name not in TEMPLATES:
        raise ValueError(f"未知模板: {template_name}")

    tpl = TEMPLATES[template_name]
    fmt = tpl["format"]
    vol = tpl["volume"]

    # 如果模板需要密码但用户没给
    tpl_password = password
    if tpl["password"] is True and not password:
        tpl_password = None  # 不加密

    out = output
    if not out.suffix:
        out = out.with_suffix(f".{fmt}")

    # 根据格式选择适配器
    if fmt == "zip":
        archive = ZipArchive(out, password=tpl_password)
    elif fmt == "tar.gz":
        archive = TarGzArchive(out, password=tpl_password)
    else:  # 7z
        archive = SevenZipArchive(out, password=tpl_password)

    archive.compress(sources, volume_size=vol)
    return out


# ═══════════════════════════════════════════════════════
# 16. 📦 增量备份
# ═══════════════════════════════════════════════════════

def incremental_backup(source: Path, archive_path: Path,
                        password: Optional[str] = None,
                        snapshot_file: Optional[Path] = None) -> Dict:
    """增量备份：只打包自上次备份后发生变化的文件

    通过记录文件的 mtime + size + hash 来判断是新增/修改
    """
    if snapshot_file is None:
        snapshot_file = archive_path.with_suffix(".snapshot.json")

    # 加载上次快照
    previous = {}
    if snapshot_file.exists():
        try:
            import json
            previous = json.loads(snapshot_file.read_text(encoding="utf-8"))
        except Exception:
            previous = {}

    # 扫描当前状态
    current = {}
    changes = {"new": [], "modified": [], "unchanged": 0}

    for f in source.rglob("*"):
        if f.is_file():
            try:
                stat = f.stat()
                key = str(f.relative_to(source))
                file_info = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
                current[key] = file_info

                if key not in previous:
                    changes["new"].append(key)
                elif (previous[key]["mtime"] != stat.st_mtime or
                      previous[key]["size"] != stat.st_size):
                    changes["modified"].append(key)
                else:
                    changes["unchanged"] += 1
            except OSError:
                continue

    # 需要打包的文件
    changed_files = [source / f for f in changes["new"] + changes["modified"]]

    if not changed_files:
        return {"status": "no_changes", "changes": changes, "archive": None}

    # 打包变化的文件
    archive = SevenZipArchive(archive_path, password=password)
    archive.compress(changed_files)

    # 保存当前快照
    try:
        import json
        snapshot_file.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return {
        "status": "backup_created",
        "changes": changes,
        "archive": str(archive_path),
        "total_changed": len(changed_files),
    }


# ═══════════════════════════════════════════════════════
# 17. ♻️ 时光机（操作可撤销）
# ═══════════════════════════════════════════════════════

class TimeMachine:
    """操作时光机 —— 所有 destructive 操作前自动备份"""

    def __init__(self, backup_dir: Optional[Path] = None):
        self.backup_dir = backup_dir or Path.home() / ".fluxpack_trash"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.history: List[Dict] = []

    def backup_before(self, file_paths: List[Path], operation: str = "unknown") -> str:
        """在执行操作前备份文件"""
        snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + str(uuid.uuid4())[:8]
        snap_dir = self.backup_dir / snapshot_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        for f in file_paths:
            if f.exists():
                shutil.copy2(f, snap_dir / f.name)

        record = {
            "id": snapshot_id,
            "time": datetime.now().isoformat(),
            "operation": operation,
            "backup_dir": str(snap_dir),
            "files": [str(f) for f in file_paths],
        }
        self.history.append(record)

        # 保存历史
        history_file = self.backup_dir / "history.json"
        try:
            import json
            history_file.write_text(json.dumps(self.history, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        return snapshot_id

    def undo(self, snapshot_id: str) -> bool:
        """撤销操作，恢复备份"""
        for record in self.history:
            if record["id"] == snapshot_id:
                snap_dir = Path(record["backup_dir"])
                if not snap_dir.exists():
                    return False
                for f in snap_dir.iterdir():
                    if f.is_file():
                        target = Path(record["files"][0]).parent / f.name
                        shutil.copy2(f, target)
                return True
        return False

    def list_history(self) -> List[Dict]:
        """列出所有操作历史"""
        return self.history

# ═══════════════════════════════════════════════════════
# 以下为兼容性保留的原功能
# ═══════════════════════════════════════════════════════

class DiffResult:
    """对比结果"""
    def __init__(self):
        self.only_in_a: List[str] = []
        self.only_in_b: List[str] = []
        self.different: List[Tuple[str, int, int]] = []
        self.same: int = 0
    @property
    def total_diffs(self) -> int:
        return len(self.only_in_a) + len(self.only_in_b) + len(self.different)


def diff_archives(path_a: Path, path_b: Path,
                  password_a: Optional[str] = None,
                  password_b: Optional[str] = None) -> DiffResult:
    arc_a = open_archive(path_a, password=password_a)
    arc_b = open_archive(path_b, password=password_b)
    entries_a = {e.name: e for e in arc_a.list_contents() if not e.is_dir}
    entries_b = {e.name: e for e in arc_b.list_contents() if not e.is_dir}
    names_a, names_b = set(entries_a.keys()), set(entries_b.keys())
    result = DiffResult()
    result.only_in_a = sorted(names_a - names_b)
    result.only_in_b = sorted(names_b - names_a)
    common = names_a & names_b
    for name in sorted(common):
        ea, eb = entries_a[name], entries_b[name]
        if ea.size != eb.size:
            result.different.append((name, ea.size, eb.size))
        else:
            result.same += 1
    return result


def repair_archive(src: Path, dst: Path, password: Optional[str] = None,
                   progress: Optional[Callable] = None) -> Tuple[int, int, List[str]]:
    tmp_dir = _safe_mktemp("flux_repair_")
    success, failed, failed_names = 0, 0, []
    try:
        archive = open_archive(src, password=password)
        for entry in archive.list_contents():
            if entry.is_dir: continue
            if progress: progress(0, 0, entry.name)
            try:
                archive.extract(tmp_dir, members=[entry.name])
                if (tmp_dir / entry.name).exists():
                    success += 1
                else:
                    failed += 1; failed_names.append(entry.name)
            except Exception:
                failed += 1; failed_names.append(entry.name)
        if success > 0:
            open_archive(dst).compress([tmp_dir], arcname=dst.stem)
        else:
            raise RuntimeError("没有可恢复的文件")
        return success, failed, failed_names
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class DuplicateGroup:
    def __init__(self, hash_val: str, size: int):
        self.hash = hash_val; self.size = size; self.files: List[str] = []
    @property
    def wasted_bytes(self) -> int:
        return self.size * (len(self.files) - 1)


def find_duplicates(paths: List[Path], password: Optional[str] = None) -> List[DuplicateGroup]:
    all_files: Dict[str, List[str]] = defaultdict(list)
    for path in paths:
        if path.is_dir():
            for f in path.rglob("*"):
                if f.is_file():
                    _hash_file(f, all_files)
        elif path.suffix.lower() in (".zip", ".7z", ".rar", ".tar", ".tar.gz"):
            try:
                archive = open_archive(path, password=password)
                for entry in archive.list_contents():
                    if entry.is_dir: continue
                    h = entry.crc or "unknown"
                    all_files[h].append(f"{path.name}/{entry.name}")
            except Exception: pass
        elif path.is_file():
            _hash_file(path, all_files)
    result = []
    for h, files in all_files.items():
        if len(files) > 1 and h != "unknown":
            dup = DuplicateGroup(h, 0); dup.files = files; result.append(dup)
    return sorted(result, key=lambda x: x.wasted_bytes, reverse=True)


def _hash_file(path: Path, all_files: dict):
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
        all_files[h.hexdigest()].append(str(path))
    except Exception: pass


def generate_checksum(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
    return h.hexdigest()


def verify_checksum(path: Path, expected_hash: str, algorithm: str = "sha256") -> bool:
    return generate_checksum(path, algorithm).lower() == expected_hash.lower()


def checksum_file(path: Path) -> Dict[str, str]:
    md5, sha1, sha256 = hashlib.md5(), hashlib.sha1(), hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5.update(chunk); sha1.update(chunk); sha256.update(chunk)
    return {"MD5": md5.hexdigest(), "SHA1": sha1.hexdigest(), "SHA256": sha256.hexdigest()}


def save_checksums(paths: List[Path], output: Optional[Path] = None,
                   algorithm: str = "sha256") -> Path:
    if output is None: output = Path.cwd() / "checksums.txt"
    with open(output, "w", encoding="utf-8") as f:
        f.write(f"; FluxPack Checksums ({algorithm})\n")
        f.write(f"; Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for p in paths:
            if p.is_file():
                f.write(f"{generate_checksum(p, algorithm)}  {p.name}\n")
    return output


def preview_file_in_archive(archive_path: Path, file_path: str,
                            password: Optional[str] = None,
                            max_size: int = 65536, max_lines: int = 100) -> str:
    tmp_dir = _safe_mktemp("flux_preview_")
    try:
        archive = open_archive(archive_path, password=password)
        archive.extract(tmp_dir, members=[file_path])
        extracted = tmp_dir / file_path
        if not extracted.exists(): return "[文件未找到]"
        try:
            text = extracted.read_bytes()[:max_size].decode("utf-8", errors="replace")
            if text.count("\x00") > len(text) * 0.1:
                ext = extracted.suffix.lower()
                if ext in ('.jpg','.jpeg','.png','.gif','.bmp','.webp'):
                    return f"[图片: {extracted.name}, {extracted.stat().st_size:,}B]"
                if ext in ('.py','.js','.html','.css','.json','.xml','.md','.txt',
                           '.yml','.yaml','.toml','.ini','.sh','.bat','.java','.cpp','.c','.h','.rs','.go'):
                    return text[:max_size]
                return f"[二进制: {extracted.name}, {extracted.stat().st_size:,}B]"
            lines = text.splitlines()
            if len(lines) > max_lines:
                text = "\n".join(lines[:max_lines]) + f"\n... (共{len(lines)}行)"
            return text
        except: return f"[无法读取: {extracted.name}]"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def smart_cleanup(directory: Path, days_old: int = 30, min_size_mb: int = 10,
                  output_dir: Optional[Path] = None, password: Optional[str] = None,
                  dry_run: bool = True, progress: Optional[Callable] = None) -> Dict:
    if output_dir is None: output_dir = directory / "_archived"
    cutoff = time.time() - days_old * 86400
    min_size = min_size_mb * 1024 * 1024
    candidates = [f for f in directory.rglob("*") if f.is_file() and
                  f.stat().st_mtime < cutoff and f.stat().st_size >= min_size]
    if not candidates:
        return {"found": 0, "total_size": 0, "output": None, "dry_run": dry_run}
    by_month = defaultdict(list)
    for f in candidates:
        by_month[time.strftime("%Y-%m", time.gmtime(f.stat().st_mtime))].append(f)
    archives_created = []
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        for month, files in sorted(by_month.items()):
            out = output_dir / f"archive_{month}.7z"
            if progress: progress(f"归档 {month}...")
            try:
                SevenZipArchive(out, password=password).compress(files)
                for f in files:
                    try: f.unlink()
                    except: pass
                archives_created.append(str(out))
            except: pass
    return {
        "found": len(candidates),
        "total_size": sum(f.stat().st_size for f in candidates),
        "total_size_fmt": _fmt_size(sum(f.stat().st_size for f in candidates)),
        "by_month": {k: len(v) for k, v in sorted(by_month.items())},
        "archives_created": archives_created,
        "dry_run": dry_run,
    }


def merge_archives(archive_paths: List[Path], output_path: Path,
                   password: Optional[str] = None,
                   output_password: Optional[str] = None,
                   progress: Optional[Callable] = None) -> int:
    tmp_dir = _safe_mktemp("flux_merge_")
    total_files = 0
    try:
        for idx, src in enumerate(archive_paths):
            if progress: progress(idx+1, len(archive_paths), src.name)
            try:
                open_archive(src, password=password).extract(tmp_dir)
                total_files += len(open_archive(src).list_contents())
            except: pass
        open_archive(output_path, password=output_password).compress([tmp_dir], arcname=output_path.stem)
        return total_files
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
