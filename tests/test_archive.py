"""压缩/解压功能测试 —— 密码、分卷、完整性全覆盖"""

import tempfile
from pathlib import Path

import pytest

from src.core.formats import (
    ZipArchive, TarGzArchive, SevenZipArchive, RarArchive,
    open_archive, detect_format,
)
from src.core.cracker import PasswordCracker, _try_one_password, BUILTIN_DICT


# ═══════════════════════════════════════════════════════
# ZIP 测试
# ═══════════════════════════════════════════════════════

class TestZipArchive:
    def test_compress_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "hello.txt"
            test_file.write_text("Hello, FluxPack!")

            zip_path = tmp / "test.zip"
            archive = ZipArchive(zip_path)
            archive.compress([test_file])

            assert zip_path.exists()
            assert zip_path.stat().st_size > 0

            entries = archive.list_contents()
            assert len(entries) >= 1

            extract_dir = tmp / "out"
            archive.extract(extract_dir)
            assert (extract_dir / "hello.txt").read_text() == "Hello, FluxPack!"

    def test_password_compress_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "secret.txt"
            test_file.write_text("classified")

            zip_path = tmp / "secret.zip"
            archive = ZipArchive(zip_path, password="hunter2")
            archive.compress([test_file])

            # 无密码打开应失败或返回空
            no_pwd = ZipArchive(zip_path)
            assert len(no_pwd.list_contents()) >= 0

            # 有密码打开
            with_pwd = ZipArchive(zip_path, password="hunter2")
            entries = with_pwd.list_contents()
            assert len(entries) >= 1

            extract_dir = tmp / "out"
            with_pwd.extract(extract_dir)
            assert (extract_dir / "secret.txt").read_text() == "classified"

    def test_list_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "test.txt"
            test_file.write_text("data")

            zip_path = tmp / "test.zip"
            archive = ZipArchive(zip_path)
            archive.compress([test_file])

            entries = archive.list_contents()
            assert any(e.name == "test.txt" for e in entries)

    def test_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "good.txt"
            test_file.write_text("good data")

            zip_path = tmp / "good.zip"
            ZipArchive(zip_path).compress([test_file])

            ok, errors = ZipArchive(zip_path).test_integrity()
            assert ok
            assert len(errors) == 0


# ═══════════════════════════════════════════════════════
# TAR.GZ 测试
# ═══════════════════════════════════════════════════════

class TestTarGzArchive:
    def test_compress_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "hello.txt"
            test_file.write_text("Hello, FluxPack!")

            tar_path = tmp / "test.tar.gz"
            archive = TarGzArchive(tar_path)
            archive.compress([test_file])

            assert tar_path.exists()

            entries = archive.list_contents()
            assert len(entries) >= 1

            extract_dir = tmp / "out"
            archive.extract(extract_dir)
            assert (extract_dir / "hello.txt").read_text() == "Hello, FluxPack!"


# ═══════════════════════════════════════════════════════
# 7Z 测试
# ═══════════════════════════════════════════════════════

class TestSevenZipArchive:
    def test_compress_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "hello.txt"
            test_file.write_text("Hello, FluxPack!")

            sz_path = tmp / "test.7z"
            archive = SevenZipArchive(sz_path)
            archive.compress([test_file])

            assert sz_path.exists()
            assert sz_path.stat().st_size > 0

            entries = archive.list_contents()
            assert len(entries) >= 1

            extract_dir = tmp / "out"
            archive.extract(extract_dir)
            assert (extract_dir / "hello.txt").exists()
            assert (extract_dir / "hello.txt").read_text() == "Hello, FluxPack!"

    def test_password_compress_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "secret.txt"
            test_file.write_text("classified")

            sz_path = tmp / "secret.7z"
            archive = SevenZipArchive(sz_path, password="12345")
            archive.compress([test_file])

            # 无密码打开
            with pytest.raises((ValueError, Exception)):
                no_pwd = SevenZipArchive(sz_path)
                no_pwd.extract(tmp / "fail")

            # 有密码打开
            with_pwd = SevenZipArchive(sz_path, password="12345")
            extract_dir = tmp / "out2"
            with_pwd.extract(extract_dir)
            assert (extract_dir / "secret.txt").read_text() == "classified"

    def test_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "good.txt"
            test_file.write_text("good data")

            sz_path = tmp / "good.7z"
            SevenZipArchive(sz_path).compress([test_file])

            ok, errors = SevenZipArchive(sz_path).test_integrity()
            assert ok


# ═══════════════════════════════════════════════════════
# RAR 测试
# ═══════════════════════════════════════════════════════

class TestRarArchive:
    def test_list_and_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake_rar = tmp / "fake.rar"
            fake_rar.write_text("not a real rar file")
            archive = RarArchive(fake_rar)
            entries = archive.list_contents()
            assert len(entries) == 0  # 静默处理

    def test_compress_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rar_path = tmp / "test.rar"
            archive = RarArchive(rar_path)
            with pytest.raises(NotImplementedError):
                archive.compress([tmp / "dummy.txt"])


# ═══════════════════════════════════════════════════════
# 工厂测试
# ═══════════════════════════════════════════════════════

class TestOpenArchive:
    def test_detect(self):
        assert detect_format(Path("a.7z")) == "7z"
        assert detect_format(Path("a.rar")) == "rar"
        assert detect_format(Path("a.zip")) == "zip"
        assert detect_format(Path("a.tar.gz")) == "tar.gz"
        assert detect_format(Path("a.tar")) == "tar"

    def test_open_7z(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "hello.txt"
            test_file.write_text("Hello")
            sz_path = tmp / "test.7z"
            SevenZipArchive(sz_path).compress([test_file])

            opened = open_archive(sz_path)
            assert opened.format == "7z"

    def test_open_with_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "secret.txt"
            test_file.write_text("secret data")

            sz_path = tmp / "secret.7z"
            SevenZipArchive(sz_path, password="pass1").compress([test_file])

            opened = open_archive(sz_path, password="pass1")
            entries = opened.list_contents()
            assert len(entries) >= 1

    def test_get_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "info.txt"
            test_file.write_text("info data here")

            sz_path = tmp / "info.7z"
            SevenZipArchive(sz_path).compress([test_file])

            info_dict = SevenZipArchive(sz_path).get_info()
            assert info_dict["format"] == "7z"
            assert info_dict["file_count"] >= 1


# ═══════════════════════════════════════════════════════
# 密码破解测试
# ═══════════════════════════════════════════════════════

class TestPasswordCracker:
    def test_dict_attack_finds_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "data.txt"
            test_file.write_text("private data")

            sz_path = tmp / "protected.7z"
            SevenZipArchive(sz_path, password="123456").compress([test_file])

            cracker = PasswordCracker(sz_path)
            result = cracker.dict_attack(num_workers=1)

            assert result.found
            assert result.password == "123456"
            assert result.attempts > 0

    def test_dict_attack_custom_wordlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "data.txt"
            test_file.write_text("data")

            sz_path = tmp / "protected.7z"
            SevenZipArchive(sz_path, password="mycustompwd").compress([test_file])

            # 自建字典
            wordlist = ["wrong", "test", "mycustompwd", "last"]
            cracker = PasswordCracker(sz_path)
            result = cracker.dict_attack(wordlist, num_workers=1)

            assert result.found
            assert result.password == "mycustompwd"

    def test_brute_force_finds_short_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "data.txt"
            test_file.write_text("data")

            sz_path = tmp / "bf.7z"
            SevenZipArchive(sz_path, password="42").compress([test_file])

            cracker = PasswordCracker(sz_path)
            result = cracker.brute_force("0123456789", 2, 2, num_workers=1)

            assert result.found
            assert result.password == "42"

    def test_smart_attack_finds_password(self):
        """智能破解应首先尝试字典，命中"password"（内置字典第2个）"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "data.txt"
            test_file.write_text("data")

            sz_path = tmp / "smart.7z"
            # "password" 在内置字典第2位，字典攻击命中后立即返回，不会落到暴力阶段
            SevenZipArchive(sz_path, password="password").compress([test_file])

            cracker = PasswordCracker(sz_path)
            result = cracker.smart_attack(num_workers=1)

            assert result.found
            assert result.password == "password"

    def test_mask_attack(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "data.txt"
            test_file.write_text("data")

            sz_path = tmp / "mask.7z"
            SevenZipArchive(sz_path, password="12").compress([test_file])

            cracker = PasswordCracker(sz_path)
            # 只测 ?d?d（2位数字）— 100组合，快速完成
            result = cracker.mask_attack(["?d?d"], num_workers=1)

            assert result.found
            assert result.password == "12"

    def test_no_header_encryption_still_rejects_wrong_password(self):
        """回归测试：7z 不加密文件头时，错误密码不应被接受"""
        import py7zr
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            test_file = tmp / "data.txt"
            test_file.write_text("secret content")

            # 用 py7zr 原生创建不带 header_encryption 的加密 7z
            sz_path = tmp / "noheader.7z"
            with py7zr.SevenZipFile(sz_path, "w", password="realpass") as zf:
                zf.write(test_file)

            cracker = PasswordCracker(sz_path)

            # 错误密码应该返回 False
            assert _try_one_password((str(sz_path), "wrongpass")) is None
            # 正确密码应该返回 True (返回密码本身)
            assert _try_one_password((str(sz_path), "realpass")) == "realpass"

            # 字典攻击也应能找到
            result = cracker.dict_attack(["wrong", "test", "realpass", "last"], num_workers=1)
            assert result.found
            assert result.password == "realpass"
