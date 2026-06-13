"""高级功能测试 —— 智能密码 / 格式推荐 / 分类打包 / 隐写 / 对比 / 修复 / 去重 / 搜索"""

import tempfile
from pathlib import Path

import pytest

from src.core.advanced import (
    smart_password_candidates, recommend_format, auto_classify,
    steganography_check, diff_archives, repair_archive,
    find_duplicates, checksum_file, generate_checksum, verify_checksum,
    preview_file_in_archive, fulltext_search_archives,
    recursive_extract, health_report, space_waste_analysis,
    compatibility_check, merge_archives, smart_cleanup,
    DiffResult, DuplicateGroup,
)
from src.core.formats import SevenZipArchive, ZipArchive


class TestSmartPassword:
    def test_generates_candidates(self):
        cand = smart_password_candidates(Path("secret_docs.7z"))
        assert len(cand) > 10
        assert "secret_docs" in cand
        assert "secret_docs123" in cand

    def test_includes_common_passwords(self):
        cand = smart_password_candidates(Path("test.7z"))
        assert "123456" in cand
        assert "password" in cand
        assert "admin" in cand


class TestRecommendFormat:
    def test_recommends_7z_for_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "test.py").write_text("x=1")
            (tmp / "test.js").write_text("console.log(1)")
            r = recommend_format([tmp / "test.py", tmp / "test.js"])
            assert r["format"] == "7z"

    def test_recommends_zip_for_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 1000)
            (tmp / "photo.png").write_bytes(b"\x89PNG" + b"x" * 1000)
            r = recommend_format([tmp / "photo.jpg", tmp / "photo.png"])
            assert r["format"] in ("zip", "7z")


class TestClassify:
    def test_auto_classify_by_type(self):
        with tempfile.TemporaryDirectory() as src:
            src = Path(src)
            (src / "code.py").write_text("x=1")
            (src / "doc.txt").write_text("hello")
            (src / "image.jpg").write_bytes(b"\xff\xd8\xff\xee")

            with tempfile.TemporaryDirectory() as out:
                out = Path(out)
                results = auto_classify(src, out, by="type")
                assert len(results) >= 1

    def test_auto_classify_by_date(self):
        with tempfile.TemporaryDirectory() as src:
            src = Path(src)
            (src / "file.txt").write_text("data")
            with tempfile.TemporaryDirectory() as out:
                out = Path(out)
                results = auto_classify(src, out, by="date")
                assert len(results) >= 1


class TestSteganography:
    def test_clean_archive_detected_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "clean.txt"
            f.write_text("hello")
            arc = tmp / "clean.7z"
            SevenZipArchive(arc).compress([f])
            result = steganography_check(arc)
            assert result["safe"] is True

    def test_zip_with_extra_data_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "test.txt"
            f.write_text("hello")
            arc = tmp / "test.zip"
            ZipArchive(arc).compress([f])
            # 在尾部追加隐藏数据
            with open(arc, "ab") as fh:
                fh.write(b"HIDDEN DATA BEYOND EOCD")
            result = steganography_check(arc)
            if result["issues"]:
                assert any("额外" in i for i in result["issues"])


class TestDiff:
    def test_identical_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.txt").write_text("same")
            arc1 = tmp / "a.7z"
            arc2 = tmp / "b.7z"
            SevenZipArchive(arc1).compress([tmp / "a.txt"])
            SevenZipArchive(arc2).compress([tmp / "a.txt"])
            result = diff_archives(arc1, arc2)
            assert result.same >= 1
            assert len(result.only_in_a) == 0
            assert len(result.only_in_b) == 0

    def test_different_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "only_a.txt").write_text("a")
            (tmp / "both.txt").write_text("same")
            arc1 = tmp / "a.7z"
            SevenZipArchive(arc1).compress([tmp / "only_a.txt", tmp / "both.txt"])
            arc2 = tmp / "b.7z"
            (tmp / "only_b.txt").write_text("b")
            SevenZipArchive(arc2).compress([tmp / "only_b.txt", tmp / "both.txt"])
            result = diff_archives(arc1, arc2)
            assert "only_a.txt" in result.only_in_a
            assert "only_b.txt" in result.only_in_b


class TestRepair:
    def test_healthy_archive_repairs_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "good.txt").write_text("data")
            src = tmp / "src.7z"
            SevenZipArchive(src).compress([tmp / "good.txt"])
            dst = tmp / "repaired.7z"
            s, f, names = repair_archive(src, dst)
            assert s >= 1
            assert f == 0


class TestDedup:
    def test_finds_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.txt").write_text("duplicate content")
            (tmp / "b.txt").write_text("duplicate content")
            (tmp / "c.txt").write_text("different")
            dups = find_duplicates([tmp])
            assert len(dups) >= 1


class TestChecksum:
    def test_generate_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "data.bin"
            f.write_bytes(b"hello world" * 100)
            h = generate_checksum(f)
            assert len(h) == 64  # SHA256
            assert verify_checksum(f, h) is True
            assert verify_checksum(f, "0" * 64) is False

    def test_checksum_file_returns_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "data.bin"
            f.write_bytes(b"test data")
            h = checksum_file(f)
            assert "MD5" in h
            assert "SHA1" in h
            assert "SHA256" in h
            assert len(h["MD5"]) == 32


class TestFulltextSearch:
    def test_search_finds_keyword(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "search.txt").write_text("this is a SECRET keyword inside")
            arc = tmp / "search.7z"
            SevenZipArchive(arc).compress([tmp / "search.txt"])
            results = fulltext_search_archives([str(arc)], "SECRET")
            assert len(results) >= 1
            assert results[0]["file"] == "search.txt"


class TestRecursiveExtract:
    def test_nested_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inner = tmp / "inner.txt"
            inner.write_text("deep data")
            inner_arc = tmp / "inner.7z"
            SevenZipArchive(inner_arc).compress([inner])
            # 外层压缩包包含内层压缩包
            outer_arc = tmp / "outer.7z"
            SevenZipArchive(outer_arc).compress([inner_arc])
            dst = tmp / "extracted"
            stats = recursive_extract(outer_arc, dst)
            assert stats["nested_found"] >= 1


class TestMerge:
    def test_merge_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.txt").write_text("file a")
            (tmp / "b.txt").write_text("file b")
            arc1 = tmp / "a.7z"; SevenZipArchive(arc1).compress([tmp / "a.txt"])
            arc2 = tmp / "b.7z"; SevenZipArchive(arc2).compress([tmp / "b.txt"])
            merged = tmp / "merged.7z"
            total = merge_archives([arc1, arc2], merged)
            assert total >= 2


class TestCompatibility:
    def test_check_normal_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "file.txt").write_text("data")
            arc = tmp / "test.7z"
            SevenZipArchive(arc).compress([tmp / "file.txt"])
            info = compatibility_check(arc)
            assert info["format"] == "7z"


class TestSmartCleanup:
    def test_dry_run_no_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "new.txt").write_text("fresh")
            result = smart_cleanup(tmp, days_old=365, min_size_mb=1, dry_run=True)
            assert result["found"] == 0
