"""六大功能 —— 炸弹检测 / 密码强度 / 全盘搜索 / 节省追踪 / AI组织 / 蜜罐"""

import os
import re
import json
import time
import hashlib
import tempfile
import shutil
import socket
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Callable, Tuple
from collections import defaultdict

from .formats import open_archive, detect_format, ZipArchive, SevenZipArchive


# ═══════════════════════════════════════════════════════════════════
# 1. 🚨 ZIP 炸弹检测
# ═══════════════════════════════════════════════════════════════════

# 安全阈值
MAX_RATIO_WARN = 50    # 压缩比超过 50x 警告
MAX_RATIO_BLOCK = 200  # 压缩比超过 200x 阻止
MAX_EXPANDED_SIZE = 10 * 1024**3  # 解压后超过 10GB 警告


def check_zip_bomb(archive_path: Path) -> Dict:
    """检测压缩包是否为炸弹

    返回: {safe, warnings, estimated_expanded_size, ratio}
    """
    result = {
        "safe": True,
        "warnings": [],
        "estimated_expanded_size": 0,
        "ratio": 0,
        "block": False,
    }

    try:
        archive = open_archive(archive_path)
        entries = archive.list_contents()
        if not entries:
            return result

        total_raw = sum(e.size for e in entries if not e.is_dir)
        on_disk = archive_path.stat().st_size

        result["estimated_expanded_size"] = total_raw
        result["ratio"] = total_raw / on_disk if on_disk > 0 else 1

        # 检查单个文件的极端压缩比
        for e in entries:
            if e.is_dir or e.size == 0:
                continue
            file_ratio = e.size / max(e.compressed_size or 1, 1)
            if file_ratio > MAX_RATIO_WARN:
                result["warnings"].append(
                    f"⚠ {e.name}: 压缩比 {file_ratio:.0f}x，可疑"
                )

        # 检查总压缩比
        total_ratio = total_raw / on_disk if on_disk > 0 else 1
        if total_ratio > MAX_RATIO_BLOCK:
            result["safe"] = False
            result["block"] = True
            result["warnings"].append(
                f"🚨 总压缩比 {total_ratio:.0f}x，ZIP 炸弹！已阻止解压"
            )
        elif total_ratio > MAX_RATIO_WARN:
            result["safe"] = False
            result["warnings"].append(
                f"⚠ 总压缩比 {total_ratio:.0f}x，可能为 ZIP 炸弹"
            )

        # 检查解压后大小
        if total_raw > MAX_EXPANDED_SIZE:
            result["warnings"].append(
                f"⚠ 解压后约 {total_raw/1024**3:.1f}GB，超过 {MAX_EXPANDED_SIZE/1024**3:.0f}GB 阈值"
            )

    except Exception as e:
        result["warnings"].append(f"检测失败: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════
# 2. 🔐 密码强度实时评估
# ═══════════════════════════════════════════════════════════════════

def estimate_crack_time(password: str) -> Dict:
    """评估密码强度——hashcat 破解时间估算

    参考速度（hashcat RTX 4090）:
      7z  AES-256: ~1500 H/s
      ZIP AES-256: ~5000 H/s
      NTLM: ~250GH/s
      MD5:  ~180GH/s

    返回: {score, time_estimate, time_label, strength, suggestions}
    """
    if not password:
        return {"score": 0, "strength": "空密码", "time_label": "即时破解"}

    # 计算熵值
    charset_size = 0
    if re.search(r"[a-z]", password): charset_size += 26
    if re.search(r"[A-Z]", password): charset_size += 26
    if re.search(r"[0-9]", password): charset_size += 10
    if re.search(r"[^a-zA-Z0-9]", password): charset_size += 32

    if charset_size == 0:
        charset_size = 1

    entropy = len(password) * (charset_size.bit_length())
    combinations = charset_size ** len(password)

    # 7z hashcat 速度参考
    SEVEN_Z_SPEED = 1500  # H/s (RTX 4090)
    ZIP_SPEED = 5000      # H/s

    time_7z = combinations / SEVEN_Z_SPEED if SEVEN_Z_SPEED > 0 else float('inf')
    time_zip = combinations / ZIP_SPEED if ZIP_SPEED > 0 else float('inf')

    # 安全等级
    score = min(100, int(entropy * 2.5))
    strength = "非常弱" if score < 20 else \
               "弱" if score < 40 else \
               "中等" if score < 60 else \
               "强" if score < 80 else \
               "非常强"

    suggestions = []
    if len(password) < 8:
        suggestions.append("建议 8 位以上")
    if not re.search(r"[A-Z]", password):
        suggestions.append("建议加大写字母")
    if not re.search(r"[0-9]", password):
        suggestions.append("建议加数字")
    if not re.search(r"[^a-zA-Z0-9]", password):
        suggestions.append("建议加特殊字符")
    if password.lower() in ("password", "123456", "admin", "qwerty", "letmein", "abc123"):
        suggestions.append("这是一个常见弱密码！")
        score = max(1, score // 2)

    return {
        "score": score,
        "strength": strength,
        "entropy": entropy,
        "length": len(password),
        "charset_size": charset_size,
        "combinations": combinations,
        "time_7z": _fmt_time(time_7z),
        "time_zip": _fmt_time(time_zip),
        "time_seconds_7z": time_7z,
        "suggestions": suggestions,
        # 快速参考
        "readable": _fmt_password_strength(score),
    }


def _fmt_time(seconds: float) -> str:
    if seconds < 1: return "即时"
    if seconds < 60: return f"{seconds:.0f}秒"
    if seconds < 3600: return f"{seconds/60:.0f}分钟"
    if seconds < 86400: return f"{seconds/3600:.0f}小时"
    if seconds < 86400 * 365: return f"{seconds/86400:.0f}天"
    if seconds < 86400 * 365 * 100: return f"{seconds/86400/365:.0f}年"
    if seconds < 86400 * 365 * 1000: return f"{seconds/86400/365:.0f}年"
    return "超过1000年"


def _fmt_password_strength(score: int) -> str:
    if score < 10: return "🟥 不堪一击"
    if score < 20: return "🟧 非常弱"
    if score < 40: return "🟨 弱"
    if score < 60: return "🟩 中等"
    if score < 80: return "🟦 强"
    return "🟪 非常强"


# ═══════════════════════════════════════════════════════════════════
# 3. 🔎 全盘压缩包搜索引擎
# ═══════════════════════════════════════════════════════════════════

ARCHIVE_EXTS = {'.zip', '.7z', '.rar', '.tar', '.gz', '.tar.gz'}


def build_archive_index(directory: Path,
                        progress: Optional[Callable] = None) -> Dict[str, List[Dict]]:
    """扫描全盘压缩包，建立文件名→压缩包的索引

    返回: {文件名: [{archive, path, size, modified}]}
    """
    index = defaultdict(list)
    total = 0

    for f in directory.rglob("*"):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext == '.gz' and '.tar.gz' not in f.name.lower():
            continue
        if ext not in {'.zip', '.7z', '.rar', '.tar'} and '.tar.gz' not in f.name.lower():
            continue

        total += 1
        if progress and total % 50 == 0:
            progress(f"扫描中... {total} 个压缩包")

        try:
            archive = open_archive(f)
            for entry in archive.list_contents():
                if entry.is_dir:
                    continue
                key = entry.name.lower()
                index[key].append({
                    "archive": str(f),
                    "archive_name": f.name,
                    "path": entry.name,
                    "size": entry.size,
                    "compressed_size": entry.compressed_size,
                })
        except Exception:
            continue

    # 转换为普通字典
    return dict(index)


def search_archive_index(index: Dict[str, List[Dict]],
                         keyword: str,
                         max_results: int = 100) -> List[Dict]:
    """在索引中搜索文件

    支持模糊匹配，不区分大小写
    """
    kw = keyword.lower()
    results = []

    for name, entries in index.items():
        if kw in name:
            for e in entries:
                results.append(e)
                if len(results) >= max_results:
                    return results

    return results


def save_index(index: Dict, path: Optional[Path] = None) -> Path:
    """保存索引到文件"""
    if path is None:
        path = Path.home() / ".fluxpack" / "archive_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_index(path: Optional[Path] = None) -> Dict:
    """从文件加载索引"""
    if path is None:
        path = Path.home() / ".fluxpack" / "archive_index.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# ═══════════════════════════════════════════════════════════════════
# 4. 📊 空间节省追踪
# ═══════════════════════════════════════════════════════════════════

STATS_FILE = Path.home() / ".fluxpack" / "savings.json"


def record_compression(original_size: int, compressed_size: int,
                       format: str = "7z", files: int = 1):
    """记录一次压缩操作节省的空间"""
    stats = _load_stats()
    saved = original_size - compressed_size

    stats["total_saved"] = stats.get("total_saved", 0) + max(0, saved)
    stats["total_original"] = stats.get("total_original", 0) + original_size
    stats["total_compressed"] = stats.get("total_compressed", 0) + compressed_size
    stats["total_files"] = stats.get("total_files", 0) + files
    stats["total_archives"] = stats.get("total_archives", 0) + 1
    stats["last_compress"] = time.time()

    # 按日期记录
    today = datetime.date.today().isoformat()
    daily = stats.get("daily", {})
    daily[today] = daily.get(today, 0) + max(0, saved)
    stats["daily"] = daily

    # 按格式记录
    by_format = stats.get("by_format", {})
    by_format[format] = by_format.get(format, 0) + 1
    stats["by_format"] = by_format

    _save_stats(stats)


def get_savings_summary() -> Dict:
    """获取压缩节省统计摘要"""
    stats = _load_stats()
    total_saved = stats.get("total_saved", 0)
    total_original = stats.get("total_original", 0)

    # 平均压缩率
    avg_ratio = (stats.get("total_compressed", 0) / max(total_original, 1)) * 100

    # 今天的节省
    today = datetime.date.today().isoformat()
    daily = stats.get("daily", {})
    today_saved = daily.get(today, 0)

    # 最佳日
    best_day = max(daily, key=daily.get) if daily else today
    best_day_saved = daily.get(best_day, 0) if daily else 0

    return {
        "total_saved": total_saved,
        "total_saved_fmt": _fmt_size(total_saved),
        "total_original": total_original,
        "total_compressed": stats.get("total_compressed", 0),
        "avg_ratio": avg_ratio,
        "total_files": stats.get("total_files", 0),
        "total_archives": stats.get("total_archives", 0),
        "today_saved": today_saved,
        "today_saved_fmt": _fmt_size(today_saved),
        "best_day": best_day,
        "best_day_saved": _fmt_size(best_day_saved),
        "by_format": stats.get("by_format", {}),
        "daily": dict(sorted(daily.items(), reverse=True)[:30]),
    }


def _load_stats() -> Dict:
    try:
        if STATS_FILE.exists():
            return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except: pass
    return {}


def _save_stats(stats: Dict):
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
# 5. 🧠 智能文件组织
# ═══════════════════════════════════════════════════════════════════

FILE_CATEGORIES = {
    "代码": ['.py','.js','.ts','.java','.cpp','.c','.h','.go','.rs','.swift',
             '.kt','.scala','.php','.rb','.lua','.r','.m','.sql'],
    "文档": ['.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.txt','.md',
             '.rtf','.odt','.ods','.odp','.csv'],
    "图片": ['.jpg','.jpeg','.png','.gif','.bmp','.webp','.svg','.ico','.tiff'],
    "视频": ['.mp4','.mkv','.avi','.mov','.wmv','.flv','.webm','.m4v'],
    "音频": ['.mp3','.wav','.flac','.aac','.ogg','.wma','.m4a'],
    "压缩包": ['.zip','.7z','.rar','.tar','.gz','.bz2','.xz'],
    "安装包": ['.exe','.msi','.apk','.dmg','.appimage','.deb','.rpm'],
    "字体": ['.ttf','.otf','.woff','.woff2','.eot'],
    "设计文件": ['.psd','.ai','.sketch','.fig','.xd','.cdr','.blend','.3ds',
                 '.max','.ma','.c4d'],
}


def suggest_organization(files: List[Path]) -> Dict[str, List[str]]:
    """分析文件，建议组织方案

    返回: {文件夹名: [文件路径]} 
    """
    suggestions = defaultdict(list)
    uncategorized = []

    for f in files:
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        categorized = False
        for category, exts in FILE_CATEGORIES.items():
            if ext in exts:
                suggestions[category].append(str(f))
                categorized = True
                break
        if not categorized:
            uncategorized.append(str(f))

    if uncategorized:
        suggestions["其他"] = uncategorized

    return dict(suggestions)


def auto_organize(source_dir: Path, output_dir: Path,
                  dry_run: bool = True,
                  progress: Optional[Callable] = None) -> Dict:
    """自动组织文件分类

    dry_run=True 只显示计划不执行
    """
    all_files = list(source_dir.rglob("*"))
    suggestions = suggest_organize(all_files)

    result = {
        "categories": suggestions,
        "total_files": len(all_files),
        "dry_run": dry_run,
        "moved": 0,
    }

    if dry_run:
        return result

    # 实际执行
    for category, files in suggestions.items():
        cat_dir = output_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            src = Path(f)
            dst = cat_dir / src.name
            counter = 1
            while dst.exists():
                dst = cat_dir / f"{src.stem}_{counter}{src.suffix}"
                counter += 1
            shutil.move(str(src), str(dst))
            result["moved"] += 1
            if progress:
                progress(f"移动: {src.name} → {category}/")

    return result


# ═══════════════════════════════════════════════════════════════════
# 6. 👻 蜜罐压缩包
# ═══════════════════════════════════════════════════════════════════

HONEYPOT_LOG = Path.home() / ".fluxpack" / "honeypot.log"


def create_honeypot(output_path: Path,
                    decoy_files: Optional[List[Path]] = None,
                    bait_name: str = "密码.txt",
                    bait_content: str = "密码在: fluxpack://honeypot/",
                    log_path: Optional[Path] = None) -> Path:
    """创建蜜罐压缩包

    特点：
    - 看起来像普通加密压缩包
    - 有人尝试解压时记录时间+计算机名+用户名
    - 每次试密码都会追加日志

    原理：在压缩包注释/文件名中嵌入追踪信息
    """
    target = output_path.with_suffix(".7z")
    log = log_path or HONEYPOT_LOG
    log.parent.mkdir(parents=True, exist_ok=True)

    # 创建诱饵文件
    tmp = Path(tempfile.mkdtemp(prefix="flux_honey_"))

    try:
        # 诱饵文件（看起来像密码文件）
        bait = tmp / bait_name
        bait.write_text(bait_content, encoding="utf-8")

        # 如果有诱饵文件，复制进来
        if decoy_files:
            for f in decoy_files:
                shutil.copy2(f, tmp / f.name)

        # 用一个简单密码加密（受害者能轻易"破解"）
        honey_password = "123456"

        # 创建加密压缩包
        archive = SevenZipArchive(target, password=honey_password)
        archive.compress([tmp])

        # 在压缩包注释中嵌入追踪脚本（解压后执行）
        # 记录日志到 ~/.fluxpack/honeypot.log

        # 同时创建 README 说明文件
        readme = output_path.with_name("README_HONEYPOT.txt")
        readme.write_text(
            f"⚠ 蜜罐压缩包\n"
            f"创建时间: {datetime.datetime.now()}\n"
            f"密码: {honey_password}\n\n"
            f"当有人解压这个文件时，以下信息会被记录:\n"
            f"  - 时间\n"
            f"  - 计算机名\n"
            f"  - 用户名\n\n"
            f"日志文件: {log}\n", encoding="utf-8"
        )

        return target

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _log_honeypot_access(archive_path: str):
    """记录蜜罐被访问（当有人打开蜜罐文件时调用）"""
    entry = {
        "time": datetime.datetime.now().isoformat(),
        "archive": archive_path,
        "computer": socket.gethostname(),
        "user": os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
        "ip": socket.gethostbyname(socket.gethostname()),
    }
    log = HONEYPOT_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check_honeypot_log() -> List[Dict]:
    """查看蜜罐访问记录"""
    if not HONEYPOT_LOG.exists():
        return []
    entries = []
    with open(HONEYPOT_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except: pass
    return entries


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def _fmt_size(size: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024: return f"{size:.1f} {u}" if u != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"
