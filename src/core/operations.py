"""格式转换与批量操作"""

import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Callable

from .archive import Archive
from .formats import open_archive, ZipArchive, SevenZipArchive, TarGzArchive


# ── 格式转换 ─────────────────────────────────────────

def convert_archive(src: Path, dst: Path,
                    src_password: Optional[str] = None,
                    dst_password: Optional[str] = None,
                    progress: Optional[Callable] = None) -> Path:
    """将压缩包从一种格式转换为另一种格式"""
    # 先解压到临时目录
    import tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="fluxpack_convert_"))

    try:
        src_archive = open_archive(src, password=src_password)
        src_archive.extract(tmp_dir)

        # 收集解压出的所有文件
        extracted = list(tmp_dir.rglob("*"))
        source_paths = [f for f in extracted if f.is_file()]

        # 如果只有文件没有目录，直接用文件列表
        # 如果有目录结构，需要保留目录树
        if not any(p.is_dir() for p in extracted):
            pass

        # 创建目标格式
        dst_archive = open_archive(dst, password=dst_password)

        if progress:
            progress(f"转换中: {src.name} → {dst.name}")

        # 压缩整个临时目录
        dst_archive.compress([tmp_dir], arcname=src.stem)

        return dst

    finally:
        # 清理临时目录
        shutil.rmtree(tmp_dir, ignore_errors=True)


def batch_convert(src_pattern: str, dst_format: str,
                  src_password: Optional[str] = None,
                  dst_password: Optional[str] = None) -> List[Path]:
    """批量转换格式"""
    import glob
    results = []
    for src_path in sorted(glob.glob(src_pattern)):
        src = Path(src_path)
        dst = src.with_suffix(f".{dst_format}")
        convert_archive(src, dst, src_password, dst_password)
        results.append(dst)
    return results


# ── 批量操作 ─────────────────────────────────────────

def batch_extract(file_pattern: str,
                  output_dir: Optional[Path] = None,
                  password: Optional[str] = None) -> List[Tuple[Path, Path]]:
    """批量解压"""
    import glob
    results = []
    for src_path in sorted(glob.glob(file_pattern)):
        src = Path(src_path)
        dst = output_dir or src.parent / src.stem
        dst.mkdir(parents=True, exist_ok=True)
        archive = open_archive(src, password=password)
        archive.extract(dst)
        results.append((src, dst))
    return results


def batch_test(file_pattern: str,
               password: Optional[str] = None) -> List[Tuple[Path, bool, List[str]]]:
    """批量校验完整性"""
    import glob
    results = []
    for src_path in sorted(glob.glob(file_pattern)):
        src = Path(src_path)
        try:
            archive = open_archive(src, password=password)
            ok, errors = archive.test_integrity()
            results.append((src, ok, errors))
        except Exception as e:
            results.append((src, False, [str(e)]))
    return results
