"""混合压缩 / 管道 / 右键菜单 / 竞赛 / 解锁 / 预设 / 模拟器 测试"""

import tempfile
from pathlib import Path
import pytest

from src.core.hybrid import hybrid_compress, image_optimized_pack, Pipeline, classify_file, analyze_files
from src.core.power import format_battle, batch_password_unlock, unlock_with_smart_candidates
from src.core.finale import load_profiles, save_profile, delete_profile, simulate_compression
from src.core.formats import SevenZipArchive


# ═══════════════════════════════════════════════════════════════════
# Hybrid
# ═══════════════════════════════════════════════════════════════════

class TestClassifyFile:
    def test_classify_text(self):
        assert classify_file(Path("test.py")) == "text"
        assert classify_file(Path("README.md")) == "text"
        assert classify_file(Path("index.html")) == "text"

    def test_classify_image(self):
        assert classify_file(Path("photo.jpg")) == "image"
        assert classify_file(Path("image.png")) == "image"

    def test_classify_executable(self):
        assert classify_file(Path("program.exe")) == "executable"

    def test_analyze_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "code.py").write_text("x=1")
            (tmp / "photo.jpg").write_bytes(b"\xff\xd8\xff")
            groups = analyze_files([tmp])
            assert "text" in groups
            assert "image" in groups


class TestHybridCompress:
    def test_hybrid_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sub = tmp / "src"
            sub.mkdir()
            (sub / "a.txt").write_text("hello world")
            (sub / "b.py").write_text("print('hi')")
            out = tmp / "hybrid.7z"
            result = hybrid_compress([sub], out)
            assert result.exists()
            assert result.stat().st_size > 0


class TestImageOptimizedPack:
    def test_pack_text_and_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "readme.txt").write_text("photo album")
            (tmp / "test.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 1000)
            out = tmp / "images.7z"
            result = image_optimized_pack([tmp], out)
            assert result.exists()


# ═══════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════

class TestPipeline:
    def test_pipeline_build_and_describe(self):
        p = Pipeline()
        p.add_download("https://example.com/file.zip")
        p.add_extract()
        p.add_clean()
        p.add_compress(output="result.7z")
        assert len(p.steps) == 4
        desc = p.describe()
        assert "管道计划" in desc
        assert "download" in desc

    def test_pipeline_from_yaml(self):
        from src.core.hybrid import pipeline_from_yaml
        text = "download url=https://x.com/file.zip\nextract\ncompress output=out.7z"
        p = pipeline_from_yaml(text)
        assert len(p.steps) == 3
        assert p.steps[0]["action"] == "download"


# ═══════════════════════════════════════════════════════════════════
# Format Battle
# ═══════════════════════════════════════════════════════════════════

class TestFormatBattle:
    def test_battle_returns_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "data.txt").write_text("benchmark data " * 100)
            results = format_battle([tmp / "data.txt"], formats=["zip", "7z"])
            assert len(results) == 2
            fmts = [r["format"] for r in results]
            assert "zip" in fmts
            assert "7z" in fmts
            for r in results:
                assert r["size"] > 0
                assert r["ratio"] > 0
                assert r["time"] > 0

    def test_battle_identifies_best(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "data.txt").write_text("x" * 5000)
            results = format_battle([tmp / "data.txt"], formats=["zip", "7z"])
            best = [r for r in results if r.get("best")]
            assert len(best) == 1


# ═══════════════════════════════════════════════════════════════════
# Batch Unlock
# ═══════════════════════════════════════════════════════════════════

class TestBatchUnlock:
    def test_unlock_with_correct_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "secret.txt"
            f.write_text("classified")
            arc = tmp / "locked.7z"
            SevenZipArchive(arc, password="opensesame").compress([f])
            result = batch_password_unlock(arc, ["wrong", "nope", "opensesame", "last"])
            assert result["found"] is True
            assert result["password"] == "opensesame"

    def test_unlock_fails_without_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "secret.txt"
            f.write_text("data")
            arc = tmp / "locked.7z"
            SevenZipArchive(arc, password="realpass").compress([f])
            result = batch_password_unlock(arc, ["wrong1", "wrong2"])
            assert result["found"] is False

    def test_unlock_with_smart_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "data.txt"
            f.write_text("data")
            arc = tmp / "smart_lock.7z"
            SevenZipArchive(arc, password="password").compress([f])
            result = unlock_with_smart_candidates(arc)
            assert result["found"] is True
            assert result["password"] == "password"


# ═══════════════════════════════════════════════════════════════════
# Profiles
# ═══════════════════════════════════════════════════════════════════

class TestProfiles:
    def test_load_defaults(self):
        profiles = load_profiles()
        assert len(profiles) >= 6
        assert "极限压缩" in profiles

    def test_save_and_delete_custom(self):
        save_profile("test_profile", {"format": "zip", "password": "", "volume": "",
                                       "hybrid": False, "level": "standard", "desc": "test"})
        profiles = load_profiles()
        assert "test_profile" in profiles
        delete_profile("test_profile")
        profiles2 = load_profiles()
        assert "test_profile" not in profiles2

    def test_cannot_delete_default(self):
        assert delete_profile("极限压缩") is False


# ═══════════════════════════════════════════════════════════════════
# Simulate
# ═══════════════════════════════════════════════════════════════════

class TestSimulate:
    def test_simulate_returns_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "data.txt").write_text("test data for simulation " * 50)
            results = simulate_compression([tmp / "data.txt"], sample_ratio=1.0)
            meta = results.pop("_meta", {})
            assert meta.get("total_files", 0) >= 1
            assert "zip" in results or "7z" in results
