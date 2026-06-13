"""核弹级功能 —— hashcat加速破解 / 后台监控 / 自解压压缩包"""

import os
import sys
import time
import json
import shutil
import signal
import tempfile
import subprocess
import threading
from pathlib import Path
from typing import List, Optional, Dict, Callable, Tuple

from .formats import open_archive, detect_format, ZipArchive, SevenZipArchive


# ═══════════════════════════════════════════════════════════════════
# 1. 🔥 hashcat GPU 加速密码破解
# ═══════════════════════════════════════════════════════════════════

# 7-Zip CLI hash 提取示例: 7z l -slt archive.7z → 提取 CRC/AES 信息
HASHCAT_7Z_MODE = "11600"     # 7z
HASHCAT_ZIP_MODE = "17220"     # ZIP AES-256
HASHCAT_RAR_MODE = "13000"     # RAR5


def find_hashcat() -> Optional[str]:
    """查找系统中已安装的 hashcat"""
    # 常见安装路径
    candidates = [
        shutil.which("hashcat"),
        shutil.which("hashcat.exe"),
        "C:\\hashcat\\hashcat.exe",
        "C:\\Program Files\\hashcat\\hashcat.exe",
        os.path.expanduser("~\\scoop\\shims\\hashcat.exe"),
        os.path.expanduser("~\\AppData\\Local\\hashcat\\hashcat.exe"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(Path(c).resolve())
    return None


def extract_7z_hash(archive_path: Path) -> Optional[str]:
    """从 7z 文件中提取 hashcat 可用的 hash"""
    seven_zip = shutil.which("7z") or "7z"
    try:
        # 7z CLI 的输出中包含加密信息
        r = subprocess.run(
            [seven_zip, "l", "-slt", str(archive_path)],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return None

        output = r.stdout

        # 提取 hash 需要的参数
        salt = ""
        iv = ""
        crc = ""
        method = ""
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Method ="): method = line.split("=", 1)[1].strip()
            if line.startswith("Salt ="): salt = line.split("=", 1)[1].strip()
            if line.startswith("InitVector ="): iv = line.split("=", 1)[1].strip()
            if line.startswith("CRC ="): crc = line.split("=", 1)[1].strip()

        if not method or "AES" not in method:
            return None

        # hashcat 7z hash 格式: $7z$0$salt$iv$crc$method$...
        # 简化版: $7z$0$salt$iv$crc$中英文与算法ID
        # 实际上我们需要用 7z2hashcat 工具或更精确的方法

        # 更可靠的方式: 用 7z CLI 输出所有参数让 hashcat 处理
        # hashcat 7z 格式: $7z$0$salt$iv$XXXX$data_length$method_index
        # 从 7z 的输出中提取足够信息

        # 对于简单的场景，我们直接用 hashcat 的 --example-hashes 模式
        # 或者让用户提供 hash

        return None  # 需要更精确的实现，用 7z2hashcat 工具

    except Exception:
        return None


def crack_with_hashcat(archive_path: Path,
                       hash_str: str,
                       hash_mode: str = HASHCAT_7Z_MODE,
                       wordlist: Optional[str] = None,
                       extra_args: Optional[List[str]] = None,
                       progress: Optional[Callable] = None) -> Dict:
    """使用 hashcat GPU 加速破解

    需要:
        1. 安装 hashcat (https://hashcat.net)
        2. 显卡驱动 (NVIDIA/AMD) 或 OpenCL runtime for CPU
        3. 字典文件

    参数:
        archive_path: 压缩包路径
        hash_str: hashcat 格式的 hash 字符串
        hash_mode: hashcat 模式 (11600=7z, 17220=ZIP)
        wordlist: 字典文件路径 (默认用内置字典+规则)
        extra_args: 额外 hashcat 参数

    返回:
        {found, password, speed, device, command}
    """
    result = {
        "found": False,
        "password": None,
        "speed": 0,
        "device": "",
        "command": "",
        "error": None,
    }

    hc = find_hashcat()
    if not hc:
        result["error"] = "未找到 hashcat。请从 https://hashcat.net 下载并安装"
        return result

    # 准备输出文件
    tmp_dir = Path(tempfile.mkdtemp(prefix="flux_hc_"))
    hash_file = tmp_dir / "hash.txt"
    out_file = tmp_dir / "found.txt"

    try:
        hash_file.write_text(hash_str, encoding="utf-8")

        # 准备命令
        cmd = [
            hc, "-m", hash_mode,
            "-a", "3" if not wordlist else "0",  # 3=mask, 0=dictionary
            str(hash_file),
            wordlist if wordlist else "?d?d?d?d?d?d",  # 6位数字
            "-o", str(out_file),
            "--potfile-disable",
            "--status",
            "--status-timer", "1",
        ]
        if extra_args:
            cmd.extend(extra_args)

        result["command"] = " ".join(cmd)

        if progress:
            progress(f"⏳ hashcat 运行中...")

        # 运行 hashcat
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=str(tmp_dir)
        )

        # 监控进度
        thread_active = [True]

        def monitor():
            while thread_active[0]:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line:
                    break
                if "Speed" in line and progress:
                    progress(f"⚡ {line.strip()}")
                if "Session" in line and progress:
                    progress(f"⚡ {line.strip()}")

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

        proc.wait()
        thread_active[0] = False

        # 检查结果
        if out_file.exists():
            found = out_file.read_text(encoding="utf-8", errors="ignore").strip()
            if found and ":" in found:
                pwd = found.split(":", 1)[1].strip()
                result["found"] = True
                result["password"] = pwd

        # 提取状态信息
        stderr_text = proc.stderr.read() if proc.stderr else ""
        for line in (proc.stdout.read() if proc.stdout else "").splitlines():
            if "Speed" in line:
                import re
                m = re.search(r"([\d.]+)\s*(\w+/s)", line)
                if m:
                    result["speed"] = f"{m.group(1)} {m.group(2)}"
                    break

    except Exception as e:
        result["error"] = str(e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


# ═══════════════════════════════════════════════════════════════════
# 2. 👁 后台文件夹监控 (Auto-Watcher)
# ═══════════════════════════════════════════════════════════════════

class ArchiveWatcher:
    """后台文件夹监控——新文件自动压缩归档"""

    def __init__(self, watch_dir: Path, output_dir: Optional[Path] = None,
                 profile: Optional[Dict] = None,
                 delete_after: bool = False,
                 poll_interval: float = 5.0):
        self.watch_dir = Path(watch_dir)
        self.output_dir = Path(output_dir or watch_dir / "_archived")
        self.profile = profile or {"format": "7z", "password": None, "hybrid": True}
        self.delete_after = delete_after
        self.poll_interval = poll_interval
        self._running = False
        self._thread = None
        self._seen = set()
        self.on_compress = None  # callback(文件名, 结果)

    def start(self):
        """启动监控（阻塞）"""
        self._running = True
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化已见文件列表
        for f in self.watch_dir.iterdir():
            if f.is_file():
                self._seen.add(f.name)

        print(f"👁 监控中: {self.watch_dir}")
        print(f"   输出: {self.output_dir}")
        print(f"   间隔: {self.poll_interval}s")
        print(f"   按 Ctrl+C 停止\n")

        while self._running:
            try:
                self._check()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ 监控错误: {e}")
                time.sleep(self.poll_interval)

    def stop(self):
        self._running = False

    def start_background(self) -> threading.Thread:
        """在后台线程启动监控"""
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()
        return self._thread

    def _check(self):
        """检查新文件"""
        new_files = []
        for f in self.watch_dir.iterdir():
            if f.is_file() and f.name not in self._seen and not f.name.startswith("."):
                new_files.append(f)
                self._seen.add(f.name)

        for f in new_files:
            # 跳过可能的临时文件（等几秒确保写完成）
            time.sleep(2)
            if not f.exists():
                continue

            try:
                out_name = f"{f.stem}_{time.strftime('%Y%m%d_%H%M%S')}.7z"
                out_path = self.output_dir / out_name

                fmt = self.profile.get("format", "7z")
                pwd = self.profile.get("password")
                hybrid = self.profile.get("hybrid", False)

                if hybrid and fmt == "7z":
                    from .hybrid import hybrid_compress
                    hybrid_compress([f], out_path, password=pwd)
                else:
                    archive = SevenZipArchive(out_path, password=pwd)
                    archive.compress([f])

                size_info = f"{out_path.stat().st_size / 1024:.0f}KB"

                if self.delete_after:
                    f.unlink()
                    status = f"✅ 已压缩并删除源文件"
                else:
                    status = f"✅ 已压缩"

                msg = f"  {status}: {f.name} → {out_name} ({size_info})"
                print(msg)

                if self.on_compress:
                    self.on_compress(f.name, {"success": True, "output": str(out_path)})

            except Exception as e:
                err = f"  ❌ 压缩失败: {f.name}: {e}"
                print(err)


# ═══════════════════════════════════════════════════════════════════
# 3. 📦 自解压压缩包 (SFX)
# ═══════════════════════════════════════════════════════════════════

def find_sfx_stub() -> Optional[Path]:
    """查找 7z SFX 模块"""
    candidates = [
        shutil.which("7z.sfx"),
        Path(shutil.which("7z") or "").parent / "7z.sfx" if shutil.which("7z") else None,
        Path("C:\\Program Files\\7-Zip\\7z.sfx"),
        Path("C:\\Program Files (x86)\\7-Zip\\7z.sfx"),
        Path(os.path.expanduser("~\\scoop\\apps\\7zip\\current\\7z.sfx")),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    return None


def create_sfx_archive(archive_path: Path, output_exe: Path,
                       extract_dir: str = ".", silent: bool = False,
                       progress: Optional[Callable] = None) -> Path:
    """创建自解压压缩包

    需要 7-Zip 安装（7z.sfx + 7z 命令行）

    原理: copy /b 7z.sfx + config + archive.7z output.exe
    """
    sfx_stub = find_sfx_stub()
    if not sfx_stub:
        # 尝试下载
        raise RuntimeError(
            "未找到 7z.sfx 模块。请安装 7-Zip 或从以下位置获取:\n"
            "https://www.7-zip.org/a/7z2409-extra.7z\n"
            "解压后把 7z.sfx 放到 FluxPack 目录下"
        )

    if progress:
        progress("创建自解压配置...")

    # SFX 配置
    config = f""";!@Install@!UTF-8!
Title="FluxPack 自解压压缩包"
ExtractDialogText="正在解压, 请稍候..."
ExtractPathStr="{extract_dir}"
ExtractTitle="FluxPack 自解压"
RunProgram=""
;!@InstallEnd@!
"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="flux_sfx_"))
    config_file = tmp_dir / "config.txt"
    config_file.write_text(config, encoding="utf-8")

    if progress:
        progress("正在合并 SFX 模块...")

    # 合并: copy /b 7z.sfx + config.txt + archive.7z output.exe
    try:
        with open(output_exe, "wb") as out:
            # 1. SFX 模块
            out.write(sfx_stub.read_bytes())
            # 2. 配置文件
            out.write(config_file.read_bytes())
            # 3. 压缩包数据
            out.write(archive_path.read_bytes())

        output_exe.chmod(0o755)

        if progress:
            size = output_exe.stat().st_size
            progress(f"✅ 自解压包已创建: {_fmt_size(size)}")

        return output_exe

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def _fmt_size(size: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024: return f"{size:.1f} {u}" if u != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"
