"""三大核弹级功能 —— 混合压缩 / 管道引擎 / 图像优化打包"""

import os
import io
import gzip
import shutil
import tempfile
import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Callable, Any
from collections import defaultdict

from .formats import open_archive, detect_format, ZipArchive, SevenZipArchive, TarGzArchive
from .archive import Archive

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False


# ═══════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════

def _fmt_size(size: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024: return f"{size:.1f} {u}" if u != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"

def _safe_mktemp(prefix="flux_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


# ═══════════════════════════════════════════════════════════════════
# 文件类型分类系统
# ═══════════════════════════════════════════════════════════════════

FILE_CATEGORIES = {
    "text": {'.txt','.md','.py','.js','.ts','.html','.css','.json','.xml','.yml','.yaml',
             '.toml','.ini','.cfg','.conf','.log','.csv','.sql','.sh','.bat','.ps1',
             '.java','.cpp','.c','.h','.rs','.go','.rb','.php','.vue','.svelte',
             '.lua','.r','.m','.swift','.kt','.scala','.tex','.bib','.rst',
             '.yaml','.yml','.env','.gitignore','.dockerignore','.editorconfig',
             '.svg','.sass','.scss','.less','.pl','.pm','.t','.sqlite'},
    "image": {'.jpg','.jpeg','.png','.gif','.bmp','.webp','.tiff','.tif','.ico',
              '.heic','.heif','.avif','.jp2','.j2k','.pcx','.tga'},
    "audio": {'.mp3','.wav','.flac','.aac','.ogg','.wma','.m4a','.opus','.ape',
              '.mid','.midi','.aiff'},
    "video": {'.mp4','.mkv','.avi','.mov','.wmv','.flv','.webm','.m4v','.mpg',
              '.mpeg','.3gp','.ogv','.ts','.mts'},
    "archive": {'.zip','.7z','.rar','.tar','.gz','.bz2','.xz','.zst','.tar.gz',
                '.tar.bz2','.tar.xz','.tgz'},
    "executable": {'.exe','.dll','.so','.dylib','.bin','.msi','.apk','.appimage',
                   '.deb','.rpm','.wasm'},
    "office": {'.doc','.docx','.xls','.xlsx','.ppt','.pptx','.pdf','.odt','.ods',
               '.odp','.pages','.numbers','.key','.rtf'},
    "font": {'.ttf','.otf','.woff','.woff2','.eot'},
    "database": {'.db','.sqlite','.sqlite3','.mdb','.accdb','.dbf'},
}

CATEGORY_ALGORITHMS = {
    "text": {"method": "PPMd", "level": 7, "reason": "PPMd 对文本压缩率远超 LZMA2"},
    "image": {"method": "store", "level": 0, "reason": "图片已经过压缩，二次压缩浪费时间"},
    "audio": {"method": "store", "level": 0, "reason": "音频已压缩，store 最快"},
    "video": {"method": "store", "level": 0, "reason": "视频已高度压缩"},
    "archive": {"method": "store", "level": 0, "reason": "已是压缩包，不再重复压缩"},
    "executable": {"method": "LZMA2", "level": 9, "reason": "LZMA2 极限压缩 exe 效果极好"},
    "office": {"method": "LZMA2", "level": 7, "reason": "Office 文件适合 LZMA2"},
    "font": {"method": "LZMA2", "level": 5, "reason": "字体文件标准压缩"},
    "database": {"method": "LZMA2", "level": 7, "reason": "数据库文件有重复模式"},
}


def classify_file(file_path: Path) -> str:
    """对文件进行分类"""
    ext = file_path.suffix.lower()
    for category, exts in FILE_CATEGORIES.items():
        if ext in exts:
            return category
    # 检查文件名
    name = file_path.name.lower()
    if name in ('makefile', 'dockerfile', 'gemfile', 'procfile'):
        return "text"
    return "binary"


def analyze_files(file_paths: List[Path]) -> Dict[str, List[Path]]:
    """分析一组文件，按类型分组"""
    groups = defaultdict(list)
    for f in file_paths:
        if f.is_file():
            cat = classify_file(f)
            groups[cat].append(f)
        elif f.is_dir():
            for sub in f.rglob("*"):
                if sub.is_file():
                    cat = classify_file(sub)
                    groups[cat].append(sub)
    return dict(groups)


# ═══════════════════════════════════════════════════════════════════
# 1. 🧬 多算法混合压缩引擎
# ═══════════════════════════════════════════════════════════════════

def hybrid_compress(sources: List[Path], output: Path,
                    password: Optional[str] = None,
                    volume_size: Optional[int] = None,
                    progress: Optional[Callable] = None) -> Path:
    """多算法混合压缩

    1. 分析所有文件，按类型分组
    2. 对每种类型执行最优预处理+压缩
    3. 合并输出为单一压缩包

    算法策略:
      - 文本 → 7z PPMd（压缩率最高）
      - 可执行文件 → 7z LZMA2 极限（exe 压缩巨量节省空间）
      - 图片/音频/视频 → store（本身就是压缩的）
      - Office/数据库 → LZMA2 高压缩率
    """
    tmp = _safe_mktemp("flux_hybrid_")
    out = output

    try:
        # 1. 收集并分类文件
        all_files = []
        for src in sources:
            if src.is_file():
                all_files.append(src)
            elif src.is_dir():
                all_files.extend(f for f in src.rglob("*") if f.is_file())

        groups = analyze_files(sources)
        if progress:
            progress(f"分析完成: {len(all_files)} 个文件, {len(groups)} 个类别")

        # 2. 对每个类别执行最优压缩
        staged_files = []  # (original_path, processed_path_in_tmp)

        for cat, files in groups.items():
            algo = CATEGORY_ALGORITHMS.get(cat, {"method": "LZMA2", "level": 5})
            cat_dir = tmp / cat
            cat_dir.mkdir(parents=True, exist_ok=True)

            if progress:
                progress(f"[{cat}] {algo['method']} Lv.{algo['level']} — {len(files)} 个文件")

            # 对于会预处里的类型，先处理再复制
            for f in files:
                rel = f.relative_to(sources[0].parent if len(sources)==1 else sources[0])
                target = cat_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)

                if cat == "image" and HAS_PIL:
                    # 图片：优化后再放进去
                    _optimize_image(f, target)
                elif cat == "text":
                    # 文本：可以先 gzip 预压缩一层，但 7z PPMd 已经很强了
                    shutil.copy2(f, target)
                else:
                    shutil.copy2(f, target)

        # 3. 用最高压缩率打包整个准备目录
        # 根据占比最重的类别选择全局 filter
        import py7zr

        cat_sizes = {cat: sum(f.stat().st_size for f in files)
                     for cat, files in groups.items()}
        dominant = max(cat_sizes, key=cat_sizes.get) if cat_sizes else "binary"

        if dominant in ("text",):
            # 文本为主 → 用 PPMd
            filters = [{"id": py7zr.FILTER_PPMD}]
        elif dominant in ("executable", "office", "database", "binary"):
            # 二进制为主 → LZMA2 极限
            filters = [{"id": py7zr.FILTER_LZMA2, "level": 9}]
        else:
            filters = None  # py7zr 默认

        try:
            with py7zr.SevenZipFile(out, "w", filters=filters,
                                     password=password or None) as szf:
                szf.writeall(tmp, arcname=out.stem)
        except Exception:
            # 降级到无 filter
            with py7zr.SevenZipFile(out, "w", password=password or None) as szf:
                szf.writeall(tmp, arcname=out.stem)

        if progress:
            ratio = out.stat().st_size / sum(f.stat().st_size for f in all_files) * 100
            progress(f"✅ 完成: {_fmt_size(out.stat().st_size)} ({ratio:.1f}%)")

        return out

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# 2. 🔄 压缩管道 (Pipeline)
# ═══════════════════════════════════════════════════════════════════

class Pipeline:
    """压缩管道引擎——链式操作"""

    STEPS = {
        "download": "下载 URL 到本地",
        "extract": "解压压缩包",
        "compress": "创建压缩包",
        "encrypt": "加密/修改密码",
        "decrypt": "解密",
        "clean": "清理垃圾文件 (DS_Store/Thumbs.db)",
        "strip_exif": "剥离图片 EXIF 数据",
        "optimize_images": "优化所有图片 (JPEG重压缩+PNG优化)",
        "dedup": "去重 (MD5)",
        "flatten": "展平目录结构",
        "rename": "批量重命名",
        "filter_by_ext": "按扩展名筛选文件",
        "split": "分卷",
        "checksum": "生成校验和",
        "report": "生成报告",
        "merge": "合并多个压缩包",
    }

    def __init__(self):
        self.steps: List[Dict] = []
        self.workdir = _safe_mktemp("flux_pipeline_")
        self._results = []

    def add(self, action: str, **params) -> "Pipeline":
        """添加一个步骤"""
        if action not in self.STEPS:
            raise ValueError(f"未知操作: {action}，可用: {', '.join(self.STEPS.keys())}")
        self.steps.append({"action": action, "params": params})
        return self

    def add_download(self, url: str) -> "Pipeline":
        return self.add("download", url=url)

    def add_extract(self, path: str = "", password: str = None) -> "Pipeline":
        return self.add("extract", path=path, password=password)

    def add_compress(self, output: str = "output.7z", format: str = None,
                     password: str = None, volume: str = None,
                     hybrid: bool = True) -> "Pipeline":
        return self.add("compress", output=output, format=format,
                        password=password, volume=volume, hybrid=hybrid)

    def add_clean(self) -> "Pipeline":
        return self.add("clean")

    def add_optimize_images(self, jpeg_quality: int = 85,
                            max_width: int = None) -> "Pipeline":
        return self.add("optimize_images", jpeg_quality=jpeg_quality,
                        max_width=max_width)

    def add_strip_exif(self) -> "Pipeline":
        return self.add("strip_exif")

    def add_dedup(self) -> "Pipeline":
        return self.add("dedup")

    def add_flatten(self) -> "Pipeline":
        return self.add("flatten")

    def add_split(self, volume: str = "10M") -> "Pipeline":
        return self.add("split", volume=volume)

    def add_filter_by_ext(self, include: str = None, exclude: str = None) -> "Pipeline":
        return self.add("filter_by_ext", include=include, exclude=exclude)

    def add_checksum(self) -> "Pipeline":
        return self.add("checksum")

    def add_report(self) -> "Pipeline":
        return self.add("report")

    def add_merge(self, patterns: List[str]) -> "Pipeline":
        return self.add("merge", patterns=patterns)

    def add_encrypt(self, password: str) -> "Pipeline":
        return self.add("encrypt", password=password)

    def _get_work_path(self) -> Path:
        """获取当前工作目录"""
        if self.steps and self.workdir:
            return self.workdir
        return self.workdir

    def describe(self) -> str:
        """生成管道描述"""
        lines = ["📋 管道计划:"]
        for i, step in enumerate(self.steps, 1):
            action = step["action"]
            params = step["params"]
            param_str = ", ".join(f"{k}={v}" for k, v in params.items() if v)
            desc = self.STEPS.get(action, action)
            lines.append(f"  {i}. {action}")
            if param_str:
                lines.append(f"     {param_str}")
            lines.append(f"     → {desc}")
        return "\n".join(lines)

    def run(self, source_paths: Optional[List[Path]] = None,
            progress: Optional[Callable] = None) -> List[Any]:
        """执行管道"""
        import glob
        import urllib.request
        import json

        current_input = source_paths or []
        self.workdir.mkdir(parents=True, exist_ok=True)
        results = []

        for idx, step in enumerate(self.steps):
            action = step["action"]
            params = step["params"]
            step_dir = self.workdir / f"step_{idx:02d}"
            step_dir.mkdir(parents=True, exist_ok=True)

            if progress:
                progress(f"[{idx+1}/{len(self.steps)}] {action}...")

            if action == "download":
                url = params["url"]
                name = url.split("/")[-1].split("?")[0] or "download"
                req = urllib.request.Request(url, headers={"User-Agent": "FluxPack/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    (step_dir / name).write_bytes(resp.read())
                current_input = [step_dir / name]
                results.append(f"📥 {name}")

            elif action == "extract":
                paths = params.get("path", "")
                pwd = params.get("password")
                srcs = current_input or [Path(p.strip()) for p in paths.split(",") if p.strip()]
                extracted = []
                for src in srcs:
                    arch = open_archive(Path(src), password=pwd)
                    dst = step_dir / src.stem
                    arch.extract(dst)
                    extracted.append(dst)
                current_input = extracted
                results.append(f"📂 解压 {len(srcs)} 个")

            elif action == "compress":
                output_path = Path(params.get("output", "output.7z"))
                pwd = params.get("password")
                volume = params.get("volume")
                hybrid = params.get("hybrid", True)

                if hybrid and current_input:
                    hybrid_compress(current_input, output_path, password=pwd,
                                    volume_size=_parse_vol(volume), progress=progress)
                else:
                    arch = open_archive(output_path, password=pwd)
                    arch.compress(current_input, volume_size=_parse_vol(volume))
                current_input = [output_path]
                results.append(f"📦 {output_path.name}")

            elif action == "clean":
                cleaned = 0
                garbage = {'.DS_Store', 'Thumbs.db', '.localized', 'desktop.ini',
                           '__MACOSX', '.Spotlight-V100', '.Trashes'}
                for src in current_input:
                    if src.is_dir():
                        for f in src.rglob("*"):
                            if f.name in garbage:
                                try:
                                    if f.is_dir(): shutil.rmtree(f)
                                    else: f.unlink()
                                    cleaned += 1
                                except: pass
                results.append(f"🧹 清理 {cleaned} 个垃圾文件")

            elif action == "strip_exif":
                stripped = 0
                for src in current_input:
                    if src.is_dir():
                        for f in src.rglob("*.jpg") or src.rglob("*.jpeg") or src.rglob("*.png"):
                            try:
                                img = Image.open(f)
                                data = list(img.getdata())
                                img_no_exif = Image.new(img.mode, img.size)
                                img_no_exif.putdata(data)
                                img_no_exif.save(f, "PNG" if f.suffix.lower() == ".png" else "JPEG", quality=95)
                                stripped += 1
                            except: pass
                results.append(f"🔐 剥离 {stripped} 张图片的 EXIF")

            elif action == "optimize_images":
                quality = params.get("jpeg_quality", 85)
                max_w = params.get("max_width")
                optimized = 0
                for src in current_input:
                    if src.is_dir():
                        for f in src.rglob("*"):
                            if f.suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
                                try:
                                    _optimize_image(f, f, quality, max_w)
                                    optimized += 1
                                except: pass
                results.append(f"🖼 优化 {optimized} 张图片")

            elif action == "dedup":
                from .advanced import find_duplicates
                dups = find_duplicates(current_input)
                removed = 0
                for g in dups:
                    for f in g.files[1:]:
                        try:
                            Path(f).unlink()
                            removed += 1
                        except: pass
                results.append(f"🔁 去重: 移除 {removed} 个重复文件")

            elif action == "flatten":
                for src in current_input:
                    if src.is_dir():
                        files = [f for f in src.rglob("*") if f.is_file()]
                        for f in files:
                            target = src / f.name
                            if target != f:
                                counter = 1
                                while target.exists():
                                    target = src / f"{f.stem}_{counter}{f.suffix}"
                                    counter += 1
                                shutil.move(str(f), str(target))
                results.append(f"📂 展平目录")

            elif action == "filter_by_ext":
                include = params.get("include", "").split(",") if params.get("include") else None
                exclude = params.get("exclude", "").split(",") if params.get("exclude") else None
                for src in current_input:
                    if src.is_dir():
                        for f in list(src.rglob("*")):
                            if f.is_file():
                                ext = f.suffix.lower()
                                if include and ext not in [e.strip() for e in include]:
                                    f.unlink()
                                if exclude and ext in [e.strip() for e in exclude]:
                                    f.unlink()
                results.append(f"🔍 筛选文件")

            elif action == "split":
                vol = params.get("volume", "10M")
                for src in current_input:
                    if src.is_file():
                        arch = SevenZipArchive(src.with_suffix(".7z.001"))
                        arch.compress([src], volume_size=_parse_vol(vol))
                results.append(f"📦 分卷 ({vol})")

            elif action == "checksum":
                hashes = {}
                for src in current_input:
                    if src.is_file():
                        h = hashlib.sha256()
                        with open(src, "rb") as f:
                            for chunk in iter(lambda: f.read(65536), b""): h.update(chunk)
                        hashes[src.name] = h.hexdigest()
                (self.workdir / "checksums.sha256").write_text(
                    json.dumps(hashes, indent=2, ensure_ascii=False))
                results.append(f"🔐 校验和已保存")

            elif action == "report":
                total = sum(f.stat().st_size if f.is_file() else
                           sum(s.stat().st_size for s in f.rglob("*") if s.is_file())
                           for f in current_input)
                report = f"📊 管道报告:\n  文件: {len(current_input)}\n  总大小: {_fmt_size(total)}"
                (self.workdir / "pipeline_report.txt").write_text(report)
                results.append(report)

            elif action == "encrypt":
                pwd = params.get("password", "")
                for src in current_input:
                    if src.is_file():
                        out = src.with_suffix(".encrypted.7z")
                        hybrid_compress([src], out, password=pwd, progress=progress)
                        src.unlink()
                        current_input = [out]
                results.append(f"🔒 已加密")

        self._results = results
        return results

    def cleanup(self):
        """清理临时文件"""
        shutil.rmtree(self.workdir, ignore_errors=True)


def pipeline_from_yaml(yaml_text: str) -> Pipeline:
    """从 YAML 格式创建管道"""
    pipe = Pipeline()
    for line in yaml_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        action = parts[0]
        kwargs = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                kwargs[k] = v
        pipe.add(action, **kwargs)
    return pipe


# ═══════════════════════════════════════════════════════════════════
# 3. 🖼 图片优化打包
# ═══════════════════════════════════════════════════════════════════

def _optimize_image(src: Path, dst: Path,
                    jpeg_quality: int = 85,
                    max_width: Optional[int] = None,
                    strip_exif: bool = True) -> bool:
    """优化单张图片

    - JPEG: 重压缩（可设质量），剥离 EXIF
    - PNG: 转换为更小的 PNG（使用 Pillow 的 optimize）
    - WebP: 保持原样或转 JPEG
    - GIF: 保持原样
    """
    if not HAS_PIL:
        # 没有 Pillow 就纯复制
        shutil.copy2(src, dst)
        return False

    try:
        img = Image.open(src)
        ext = src.suffix.lower()

        # 转为 RGB（去掉 alpha 通道可以减少大小，但对 PNG 保留）
        if ext in ('.jpg', '.jpeg', '.webp'):
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

        # 缩放
        if max_width and img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # 保存
        save_kwargs = {}
        if ext in ('.jpg', '.jpeg'):
            save_kwargs["quality"] = jpeg_quality
            save_kwargs["optimize"] = True
            if strip_exif:
                save_kwargs["exif"] = b""
            img.save(dst, "JPEG", **save_kwargs)
        elif ext == '.png':
            img.save(dst, "PNG", optimize=True)
        elif ext == '.webp':
            save_kwargs["quality"] = jpeg_quality
            img.save(dst, "WEBP", **save_kwargs)
        else:
            shutil.copy2(src, dst)

        # 验证是否真的变小了
        if dst.exists() and src != dst:
            if dst.stat().st_size > src.stat().st_size:
                # 反而变大→用原文件
                shutil.copy2(src, dst)

        return True

    except Exception:
        shutil.copy2(src, dst)
        return False


def image_optimized_pack(sources: List[Path], output: Path,
                         jpeg_quality: int = 85,
                         max_width: Optional[int] = None,
                         strip_exif: bool = True,
                         password: Optional[str] = None,
                         progress: Optional[Callable] = None) -> Path:
    """图片优化打包——专为摄影师/设计师设计

    1. 扫描所有文件
    2. 对图片执行优化（JPEG重压缩/PNG优化/EXIF剥离/缩放）
    3. 非图片文件保持原样
    4. 使用 7z 最高压缩率打包
    """
    tmp = _safe_mktemp("flux_imagepack_")
    total_optimized = 0
    total_saved = 0

    try:
        # 收集文件
        all_files = []
        for src in sources:
            if src.is_file():
                all_files.append(src)
            elif src.is_dir():
                all_files.extend(f for f in src.rglob("*") if f.is_file())

        if progress:
            progress(f"🔍 扫描到 {len(all_files)} 个文件")

        # 处理每个文件
        for f in all_files:
            rel = f.relative_to(sources[0].parent if len(sources) == 1 else sources[0])
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)

            is_image = f.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.gif','.bmp','.tiff')

            if is_image:
                before = f.stat().st_size
                _optimize_image(f, target, jpeg_quality, max_width, strip_exif)
                after = target.stat().st_size
                saved = before - after
                total_optimized += 1
                total_saved += saved
                if progress and saved > 0:
                    progress(f"  🖼 {f.name}: {_fmt_size(before)} → {_fmt_size(after)} (省 {_fmt_size(saved)})")
            else:
                shutil.copy2(f, target)

        if progress:
            progress(f"✅ 优化 {total_optimized} 张图片, 节省 {_fmt_size(total_saved)}")

        # 打包
        arch = SevenZipArchive(output, password=password)
        arch.compress([tmp], arcname=output.stem)

        if progress:
            progress(f"📦 打包完成: {_fmt_size(output.stat().st_size)}")

        return output

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def _parse_vol(s):
    if not s: return None
    s = str(s).upper().strip()
    if s.endswith("G"): return int(float(s[:-1]) * 1024**3)
    if s.endswith("M"): return int(float(s[:-1]) * 1024**2)
    if s.endswith("K"): return int(float(s[:-1]) * 1024)
    try: return int(s)
    except: return None
