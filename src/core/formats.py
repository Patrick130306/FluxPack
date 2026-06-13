"""各压缩格式的适配器实现 —— 密码、分卷、完整性校验全支持"""

import zipfile
import tarfile
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple

import py7zr
import rarfile
import pyzipper

from .archive import Archive, ArchiveEntry


# ═══════════════════════════════════════════════════════
# ZIP 适配器
# ═══════════════════════════════════════════════════════

class ZipArchive(Archive):
    """ZIP 格式适配器 (pyzipper AES-256)"""

    @property
    def format(self) -> str:
        return "zip"

    @property
    def supports_password(self) -> bool:
        return True

    @property
    def supports_volumes(self) -> bool:
        return True  # 通过分卷文件实现

    def _open_read(self):
        """打开 ZIP 读取，支持密码"""
        if self.password:
            zf = pyzipper.AESZipFile(self.path, "r")
            zf.setpassword(self.password.encode())
            return zf
        # 先试普通 zipfile（兼容常用 ZIP）
        try:
            return zipfile.ZipFile(self.path, "r")
        except Exception:
            zf = pyzipper.AESZipFile(self.path, "r")
            return zf

    def list_contents(self) -> List[ArchiveEntry]:
        try:
            zf = self._open_read()
        except Exception:
            return []
        entries = []
        with zf:
            for info in zf.infolist():
                entries.append(ArchiveEntry(
                    name=info.filename,
                    size=info.file_size,
                    compressed_size=info.compress_size,
                    is_dir=info.filename.endswith("/"),
                    crc=f"{info.CRC:08x}" if info.CRC else None,
                ))
        return entries

    def extract(self, target_dir: Path, members: Optional[List[str]] = None) -> None:
        try:
            zf = self._open_read()
        except (RuntimeError, TypeError) as e:
            # 密码错误
            if "password" in str(e).lower():
                raise ValueError("密码错误，无法解压") from e
            raise
        with zf:
            zf.extractall(target_dir, members=members, pwd=self.password.encode() if self.password else None)

    def compress(self, source_paths: List[Path],
                 arcname: Optional[str] = None,
                 volume_size: Optional[int] = None) -> List[Path]:
        if self.password:
            zf = pyzipper.AESZipFile(self.path, "w",
                                     compression=pyzipper.ZIP_DEFLATED,
                                     encryption=pyzipper.WZ_AES)
            zf.setpassword(self.password.encode())
        else:
            zf = zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED)
        with zf:
            for src in source_paths:
                name = arcname or src.name
                if src.is_dir():
                    for f in src.rglob("*"):
                        arc = str(f.relative_to(src.parent))
                        if self.password:
                            zf.write(f, arc)
                        else:
                            zf.write(f, arc)
                else:
                    zf.write(src, name)

        result = [self.path]

        # 分卷: 将文件拆分为多个分卷
        if volume_size and self.path.stat().st_size > volume_size:
            result = self._split_volume(self.path, volume_size)

        return result

    @staticmethod
    def _split_volume(filepath: Path, volume_size: int) -> List[Path]:
        """将文件拆分为分卷"""
        parts = []
        idx = 0
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(volume_size)
                if not chunk:
                    break
                part_path = filepath.with_suffix(f".z{idx:02d}")
                part_path.write_bytes(chunk)
                parts.append(part_path)
                idx += 1
        # 删除原文件（已被拆分为分卷）
        filepath.unlink()
        return parts

    def test_integrity(self) -> Tuple[bool, List[str]]:
        errors = []
        try:
            zf = self._open_read()
        except Exception as e:
            return False, [f"无法打开: {e}"]
        with zf:
            for info in zf.infolist():
                try:
                    data = zf.read(info.filename, pwd=self.password.encode() if self.password else None)
                except Exception as e:
                    errors.append(f"{info.filename}: {e}")
        return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════
# TAR.GZ / TAR 适配器
# ═══════════════════════════════════════════════════════

class TarGzArchive(Archive):
    """TAR.GZ 格式适配器（不支持密码，用外挂加密）"""

    @property
    def format(self) -> str:
        return "tar.gz"

    @property
    def supports_password(self) -> bool:
        return False

    def list_contents(self) -> List[ArchiveEntry]:
        entries = []
        try:
            with tarfile.open(self.path, "r:*") as tf:
                for m in tf.getmembers():
                    entries.append(ArchiveEntry(
                        name=m.name,
                        size=m.size,
                        is_dir=m.isdir(),
                    ))
        except Exception:
            pass
        return entries

    def extract(self, target_dir: Path, members: Optional[List[str]] = None) -> None:
        with tarfile.open(self.path, "r:*") as tf:
            tf.extractall(target_dir, members=members)

    def compress(self, source_paths: List[Path],
                 arcname: Optional[str] = None,
                 volume_size: Optional[int] = None) -> List[Path]:
        mode = "w:gz"
        if self.path.suffix == ".tar":
            mode = "w"
        with tarfile.open(self.path, mode) as tf:
            for src in source_paths:
                name = arcname or src.name
                tf.add(src, arcname=name)
        return [self.path]

    def test_integrity(self) -> Tuple[bool, List[str]]:
        errors = []
        try:
            with tarfile.open(self.path, "r:*") as tf:
                for m in tf.getmembers():
                    try:
                        _ = tf.extractfile(m)
                    except Exception as e:
                        errors.append(f"{m.name}: {e}")
        except Exception as e:
            return False, [f"无法打开: {e}"]
        return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════
# 7Z 适配器
# ═══════════════════════════════════════════════════════

class SevenZipArchive(Archive):
    """7Z 格式适配器 (py7zr) — 支持 AES-256 加密"""

    @property
    def format(self) -> str:
        return "7z"

    @property
    def supports_password(self) -> bool:
        return True

    @property
    def supports_volumes(self) -> bool:
        return True

    def _open_kwargs(self):
        kwargs = {}
        if self.password:
            kwargs["password"] = self.password
        return kwargs

    def list_contents(self) -> List[ArchiveEntry]:
        try:
            with py7zr.SevenZipFile(self.path, "r", **self._open_kwargs()) as szf:
                return [
                    ArchiveEntry(
                        name=info.filename,
                        size=info.uncompressed,
                        compressed_size=info.compressed,
                        is_dir=info.filename.endswith("/"),
                    )
                    for info in szf.list()
                ]
        except py7zr.exceptions.Bad7zFile:
            return []
        except Exception:
            return []

    def extract(self, target_dir: Path, members: Optional[List[str]] = None) -> None:
        try:
            with py7zr.SevenZipFile(self.path, "r", **self._open_kwargs()) as szf:
                szf.extract(path=target_dir, targets=members)
        except py7zr.exceptions.PasswordRequired:
            raise ValueError("此文件需要密码") from None
        except py7zr.exceptions.WrongPassword:
            raise ValueError("密码错误") from None

    def compress(self, source_paths: List[Path],
                 arcname: Optional[str] = None,
                 volume_size: Optional[int] = None) -> List[Path]:
        kwargs = {}
        if self.password:
            kwargs["password"] = self.password
            kwargs["header_encryption"] = True
        if volume_size:
            kwargs["volume"] = volume_size

        with py7zr.SevenZipFile(self.path, "w", **kwargs) as szf:
            for src in source_paths:
                name = arcname or src.name
                if src.is_dir():
                    szf.writeall(src, name)
                else:
                    szf.write(src, name)

        # 收集分卷文件
        result = [self.path]
        if volume_size:
            # py7zr 原生分卷创建的文件: .7z.001, .7z.002, ...
            base = self.path
            i = 1
            volumes = []
            while True:
                vol = base.with_suffix(f".7z.{i:03d}")
                if vol.exists():
                    volumes.append(vol)
                    i += 1
                else:
                    break
            if volumes:
                result = [base.with_suffix(f".7z.001")] + volumes[1:] if volumes else [self.path]

        return result

    def test_integrity(self) -> Tuple[bool, List[str]]:
        try:
            with py7zr.SevenZipFile(self.path, "r", **self._open_kwargs()) as szf:
                result = szf.test()
                if result is None or result is True:
                    return (True, [])
                return (False, ["完整性校验失败"] if isinstance(result, bool) else [str(result)])
        except Exception as e:
            return (False, [str(e)])


# ═══════════════════════════════════════════════════════
# RAR 适配器
# ═══════════════════════════════════════════════════════

class RarArchive(Archive):
    """RAR 格式适配器 (rarfile) — 读取支持密码，压缩需 CLI"""

    @property
    def format(self) -> str:
        return "rar"

    @property
    def supports_password(self) -> bool:
        return True

    @property
    def supports_volumes(self) -> bool:
        return True  # rarfile 自动识别 .partN.rar

    def _open_kwargs(self):
        return {}  # rarfile 的密码通过 extract/open 的 pwd 参数传入

    def list_contents(self) -> List[ArchiveEntry]:
        try:
            with rarfile.RarFile(self.path) as rf:
                return [
                    ArchiveEntry(
                        name=info.filename,
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        is_dir=info.isdir(),
                        crc=f"{info.CRC:08x}" if info.CRC else None,
                    )
                    for info in rf.infolist()
                ]
        except rarfile.Error:
            return []

    def extract(self, target_dir: Path, members: Optional[List[str]] = None) -> None:
        pwd = self.password.encode() if self.password else None
        try:
            with rarfile.RarFile(self.path) as rf:
                rf.extractall(target_dir, members=members, pwd=pwd)
        except rarfile.RarCannotExec:
            raise RuntimeError("需要安装 WinRAR/UnRAR CLI，请访问 https://www.rarlab.com")
        except rarfile.BadRarFile:
            raise ValueError("RAR 文件损坏或密码错误")

    def compress(self, source_paths: List[Path],
                 arcname: Optional[str] = None,
                 volume_size: Optional[int] = None) -> List[Path]:
        """RAR 压缩需要系统安装 unrar/rar 命令行工具"""
        raise NotImplementedError(
            "RAR 压缩需要安装 WinRAR/rar CLI（rarfile 库仅支持解压）。"
            "如需创建加密压缩包，请使用 7Z 格式（AES-256 更安全）"
        )

    def test_integrity(self) -> Tuple[bool, List[str]]:
        errors = []
        pwd = self.password.encode() if self.password else None
        try:
            with rarfile.RarFile(self.path) as rf:
                for info in rf.infolist():
                    if info.isdir():
                        continue
                    try:
                        data = rf.read(info, pwd=pwd)
                        if info.CRC:
                            actual = hashlib.crc32(data) & 0xFFFFFFFF
                            if actual != info.CRC:
                                errors.append(f"{info.filename}: CRC 不匹配")
                    except Exception as e:
                        errors.append(f"{info.filename}: {e}")
        except Exception as e:
            return False, [f"无法打开: {e}"]
        return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════
# TAR 适配器（无压缩）
# ═══════════════════════════════════════════════════════

class TarArchive(TarGzArchive):
    """TAR 格式（无压缩）"""

    @property
    def format(self) -> str:
        return "tar"

    def compress(self, source_paths, arcname=None, volume_size=None):
        with tarfile.open(self.path, "w") as tf:
            for src in source_paths:
                name = arcname or src.name
                tf.add(src, arcname=name)
        return [self.path]


# ═══════════════════════════════════════════════════════
# 自动检测 & 工厂
# ═══════════════════════════════════════════════════════

def detect_format(path: Path) -> str:
    """根据文件后缀自动检测压缩格式"""
    suffix = path.suffix.lower()
    suffixes = path.suffixes

    # 分卷文件: .7z.001, .7z.002, .z01, .part1.rar
    if len(suffixes) >= 2:
        # .7z.001, .7z.002
        if suffixes[-2] == ".7z" and suffixes[-1].startswith(".") and suffixes[-1][1:].isdigit():
            return "7z"
        # .z01, .z02 （ZIP 分卷）
        if suffixes[-1].startswith(".z") and suffixes[-1][2:].isdigit():
            return "zip"
        # .part1.rar
        if suffixes[-1].startswith(".part") and suffixes[-1].strip(".part").isdigit():
            return "rar"

    if suffix == ".zip":
        return "zip"
    if suffix == ".gz" or suffixes[-2:] == [".tar", ".gz"]:
        return "tar.gz"
    if suffix == ".tar":
        return "tar"
    if suffix == ".7z":
        return "7z"
    if suffix == ".rar":
        return "rar"
    raise ValueError(f"不支持的格式: {path.name}")


def open_archive(path: Path, password: Optional[str] = None) -> Archive:
    """工厂方法 —— 根据文件自动选择适配器"""
    fmt = detect_format(path)
    if fmt == "zip":
        return ZipArchive(path, password=password)
    if fmt == "tar":
        return TarArchive(path, password=password)
    if fmt == "tar.gz":
        return TarGzArchive(path, password=password)
    if fmt == "7z":
        return SevenZipArchive(path, password=password)
    if fmt == "rar":
        return RarArchive(path, password=password)
    raise NotImplementedError(f"格式 {fmt} 尚未实现")
