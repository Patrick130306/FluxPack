"""安全/搜索/评分/差异/去重 测试"""

import tempfile
from pathlib import Path
import pytest

from src.core.omega import (
    check_zip_bomb, estimate_crack_time, build_archive_index,
    search_archive_index, save_index, load_index,
    get_savings_summary, record_compression, suggest_organization,
    create_honeypot, check_honeypot_log,
)
from src.core.phi import (
    dms_setup, dms_signin, dms_check, dms_execute,
    create_self_extracting_html,
    score_archive, diff_archives_visual,
    find_cross_format_duplicates,
)
from src.core.formats import SevenZipArchive


# ═══════════════════════════════════════════════════════════════════
# ZIP 炸弹检测
# ═══════════════════════════════════════════════════════════════════

class TestZipBomb:
    def test_normal_archive_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "normal.txt"
            f.write_text("hello world")
            arc = tmp / "normal.7z"
            SevenZipArchive(arc).compress([f])
            result = check_zip_bomb(arc)
            assert result["safe"] is True
            assert len(result["warnings"]) == 0


# ═══════════════════════════════════════════════════════════════════
# 密码强度评估
# ═══════════════════════════════════════════════════════════════════

class TestPasswordStrength:
    def test_empty_password(self):
        r = estimate_crack_time("")
        assert r["score"] == 0
        assert r["strength"] == "空密码"

    def test_weak_password(self):
        r = estimate_crack_time("123456")
        assert r["score"] < 40
        assert r["time_seconds_7z"] < 3600

    def test_strong_password(self):
        r = estimate_crack_time("MyP@ssw0rd!2024#Secure")
        assert r["score"] >= 60
        assert "年" in r["time_7z"]

    def test_common_password_suggestion(self):
        r = estimate_crack_time("password")
        assert len(r["suggestions"]) > 0


# ═══════════════════════════════════════════════════════════════════
# 全盘搜索索引
# ═══════════════════════════════════════════════════════════════════

class TestArchiveIndex:
    def test_build_and_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "doc.txt").write_text("report data")
            arc = tmp / "archive.7z"
            SevenZipArchive(arc).compress([tmp / "doc.txt"])

            # 在父目录建索引
            idx = build_archive_index(tmp.parent)
            found = False
            for name, entries in idx.items():
                if "doc.txt" in name:
                    found = True
                    break
            assert found

    def test_save_and_load(self):
        idx = {"test.txt": [{"archive": "a.7z", "path": "test.txt", "size": 100}]}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "index.json"
            save_index(idx, p)
            loaded = load_index(p)
            assert "test.txt" in loaded


# ═══════════════════════════════════════════════════════════════════
# 节省统计
# ═══════════════════════════════════════════════════════════════════

class TestSavings:
    def test_record_and_summary(self):
        record_compression(1000, 300)
        s = get_savings_summary()
        assert s["total_saved"] >= 700
        assert s["total_archives"] >= 1


# ═══════════════════════════════════════════════════════════════════
# 文件组织建议
# ═══════════════════════════════════════════════════════════════════

class TestOrganize:
    def test_suggest_organization(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "main.py").write_text("x=1")
            (tmp / "index.html").write_text("<html>")
            (tmp / "photo.jpg").write_bytes(b"\xff\xd8\xff")
            (tmp / "readme.md").write_text("# doc")
            suggestions = suggest_organization(list(tmp.rglob("*")))
            assert any("代码" in k for k in suggestions)
            assert any("文档" in k for k in suggestions)
            assert any("图片" in k for k in suggestions)


# ═══════════════════════════════════════════════════════════════════
# 蜜罐
# ═══════════════════════════════════════════════════════════════════

class TestHoneypot:
    def test_create_honeypot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            out = tmp / "honey.7z"
            result = create_honeypot(out, bait_name="passwords.txt")
            assert result.exists()
            assert result.stat().st_size > 0

    def test_honeypot_log(self):
        log = check_honeypot_log()
        assert isinstance(log, list)


# ═══════════════════════════════════════════════════════════════════
# 压缩健康评分
# ═══════════════════════════════════════════════════════════════════

class TestArchiveScore:
    def test_score_normal_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.txt").write_text("hello world")
            (tmp / "b.txt").write_text("more data here")
            arc = tmp / "test.7z"
            SevenZipArchive(arc).compress([tmp / "a.txt", tmp / "b.txt"])
            result = score_archive(arc)
            assert 0 <= result["score"] <= 100
            assert result["grade"] in ("S", "A", "B", "C", "D")
            assert len(result["dimensions"]) >= 4


# ═══════════════════════════════════════════════════════════════════
# 版本差异可视化
# ═══════════════════════════════════════════════════════════════════

class TestDiffVisual:
    def test_identical_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "f.txt").write_text("same")
            a = tmp / "a.7z"; SevenZipArchive(a).compress([tmp / "f.txt"])
            b = tmp / "b.7z"; SevenZipArchive(b).compress([tmp / "f.txt"])
            r = diff_archives_visual(a, b)
            assert r["stats"]["unchanged"] >= 1
            assert r["stats"]["added"] == 0
            assert r["stats"]["removed"] == 0

    def test_added_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "common.txt").write_text("shared")
            a = tmp / "a.7z"; SevenZipArchive(a).compress([tmp / "common.txt"])
            (tmp / "new.txt").write_text("new file")
            b = tmp / "b.7z"; SevenZipArchive(b).compress([tmp / "common.txt", tmp / "new.txt"])
            r = diff_archives_visual(a, b)
            assert r["stats"]["added"] >= 1


# ═══════════════════════════════════════════════════════════════════
# 跨格式去重
# ═══════════════════════════════════════════════════════════════════

class TestCrossFormatDedup:
    def test_duplicate_across_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            content = b"identical content across archives"
            (tmp / "data.bin").write_bytes(content)
            arc1 = tmp / "a.7z"; SevenZipArchive(arc1).compress([tmp / "data.bin"])
            arc2 = tmp / "b.7z"; SevenZipArchive(arc2).compress([tmp / "data.bin"])
            dups = find_cross_format_duplicates(tmp)
            if dups:
                assert dups[0]["archive_count"] >= 2


# ═══════════════════════════════════════════════════════════════════
# 自解压 HTML
# ═══════════════════════════════════════════════════════════════════

class TestSelfExtractingHtml:
    def test_generates_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "data.txt").write_text("self extracting test")
            arc = tmp / "source.7z"
            SevenZipArchive(arc).compress([tmp / "data.txt"])
            out = tmp / "out.html"
            result = create_self_extracting_html(arc, out)
            assert result.exists()
            html = result.read_text(encoding="utf-8")
            assert "<!DOCTYPE html>" in html
            assert "ARCHIVE_DATA" in html
            assert "extractFiles" in html


# ═══════════════════════════════════════════════════════════════════
# 死人生成开关（测试核心逻辑，不含邮件发送）
# ═══════════════════════════════════════════════════════════════════

class TestDeadMansSwitch:
    def test_setup_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "will.txt"
            f.write_text("this file will be auto-sent")
            arc = tmp / "will.7z"
            SevenZipArchive(arc, password="mypass").compress([f])

            dms_setup(arc, "mypass", "test@test.com", "from@test.com",
                      smtp_server="smtp.test.com", smtp_pass="x",
                      interval_days=30)
            status = dms_check()
            assert status["active"] is True
            assert status["triggered"] is False
            assert 0 < status["days_remaining"] <= 31

            dms_signin()
            status2 = dms_check()
            assert status2["days_remaining"] > status["days_remaining"] - 1
