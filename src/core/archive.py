"""压缩包抽象层 —— 统一所有格式的操作接口"""

from pathlib import Path
from typing import List, Optional, Tuple


class ArchiveEntry:
    """压缩包内的单个文件条目"""

    def __init__(self, name: str, size: int = 0,
                 compressed_size: Optional[int] = None,
                 is_dir: bool = False, crc: Optional[str] = None):
        self.name = name
        self.size = size
        self.compressed_size = compressed_size
        self.is_dir = is_dir
        self.crc = crc

    @property
    def ratio(self) -> Optional[float]:
        if self.compressed_size and self.size > 0:
            return self.compressed_size / self.size
        return None

    def __repr__(self):
        return f"<ArchiveEntry {self.name} ({self.size} bytes)>"


class Archive:
    """压缩包抽象基类"""

    def __init__(self, path: Path, password: Optional[str] = None):
        self.path = path
        self.password = password

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def format(self) -> str:
        raise NotImplementedError

    @property
    def supports_password(self) -> bool:
        """当前格式是否支持密码保护"""
        return False

    @property
    def supports_volumes(self) -> bool:
        """当前格式是否支持分卷"""
        return False

    # ── 核心操作 ──────────────────────────────────────

    def list_contents(self) -> List[ArchiveEntry]:
        """列出压缩包内容"""
        raise NotImplementedError

    def extract(self, target_dir: Path, members: Optional[List[str]] = None) -> None:
        """解压到目标目录"""
        raise NotImplementedError

    def compress(self, source_paths: List[Path],
                 arcname: Optional[str] = None,
                 volume_size: Optional[int] = None) -> List[Path]:
        """创建压缩包，返回所有分卷文件路径。
        volume_size: 分卷大小（字节），None 表示不分卷
        """
        raise NotImplementedError

    # ── 高级功能 ──────────────────────────────────────

    def test_integrity(self) -> Tuple[bool, List[str]]:
        """校验压缩包完整性。返回 (是否通过, 错误信息列表)"""
        raise NotImplementedError

    def get_info(self) -> dict:
        """获取压缩包详细信息"""
        entries = self.list_contents()
        total_raw = sum(e.size for e in entries if not e.is_dir)
        total_comp = sum(e.compressed_size or 0 for e in entries if not e.is_dir)
        file_count = sum(1 for e in entries if not e.is_dir)
        dir_count = sum(1 for e in entries if e.is_dir)

        return {
            "path": str(self.path),
            "format": self.format,
            "file_count": file_count,
            "dir_count": dir_count,
            "total_raw": total_raw,
            "total_compressed": total_comp,
            "ratio": (total_comp / total_raw * 100) if total_raw > 0 else 0,
            "size_on_disk": self.path.stat().st_size,
            "entries": entries,
        }
