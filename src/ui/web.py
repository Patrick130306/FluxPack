"""FluxPack Web 界面后端 —— FastAPI"""

import os
import sys
import json
import asyncio
import uuid
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# ── 后端核心 ──────────────────────────────────────────

from src.core.formats import open_archive, detect_format
from src.core.cracker import PasswordCracker
from src.core.operations import convert_archive, batch_extract, batch_test


# ── 运行中的任务状态 ──────────────────────────────────

_task_progress: dict = {}


# ── App ───────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="FluxPack Web UI", version="0.2.0")


# ── 模板 ──────────────────────────────────────────────

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")
    return html


@app.get("/api/version")
async def version():
    return {"version": "0.2.0", "name": "FluxPack"}


# ── List ──────────────────────────────────────────────

@app.post("/api/list")
async def api_list(request: Request):
    data = await request.json()
    path = data.get("path", "")
    password = data.get("password") or None

    p = Path(path)
    if not p.exists():
        return {"error": f"文件不存在: {path}"}

    try:
        archive = open_archive(p, password=password)
        entries = archive.list_contents()
        info = archive.get_info()
        return {
            "entries": [
                {
                    "name": e.name,
                    "size": e.size,
                    "compressed_size": e.compressed_size,
                    "is_dir": e.is_dir,
                    "ratio": e.ratio,
                    "crc": e.crc,
                }
                for e in entries
            ],
            "info": {
                "format": info["format"],
                "file_count": info["file_count"],
                "total_raw": info["total_raw"],
                "total_compressed": info["total_compressed"],
                "ratio": info["ratio"],
                "size_on_disk": info["size_on_disk"],
                "supports_password": archive.supports_password,
                "supports_volumes": archive.supports_volumes,
            },
            "name": p.name,
        }
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"无法打开: {e}"}


# ── Extract ───────────────────────────────────────────

@app.post("/api/extract")
async def api_extract(request: Request):
    data = await request.json()
    path = data.get("path", "")
    target = data.get("target", "")
    password = data.get("password") or None

    p = Path(path)
    dst = Path(target) if target else p.parent / p.stem

    if not p.exists():
        return {"error": f"文件不存在: {path}"}

    try:
        dst.mkdir(parents=True, exist_ok=True)
        archive = open_archive(p, password=password)
        archive.extract(dst)
        return {"success": True, "target": str(dst)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# ── Compress ──────────────────────────────────────────

@app.post("/api/compress")
async def api_compress(request: Request):
    data = await request.json()
    output = data.get("output", "")
    sources = data.get("sources", [])
    password = data.get("password") or None
    volume = data.get("volume") or None

    out = Path(output)
    srcs = [Path(s) for s in sources]

    # 校验源文件
    missing = [str(s) for s in srcs if not s.exists()]
    if missing:
        return {"error": f"源文件不存在: {', '.join(missing)}"}

    # 补后缀
    try:
        fmt = detect_format(out)
    except ValueError:
        out = out.with_suffix(".7z")

    try:
        archive = open_archive(out, password=password)
        results = archive.compress(srcs, volume_size=_parse_volume(volume))

        files = []
        for r in results:
            files.append({"name": r.name, "size": r.stat().st_size})

        return {"success": True, "files": files}
    except NotImplementedError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# ── Info ──────────────────────────────────────────────

@app.post("/api/info")
async def api_info(request: Request):
    data = await request.json()
    path = data.get("path", "")
    password = data.get("password") or None

    p = Path(path)
    if not p.exists():
        return {"error": f"文件不存在: {path}"}

    try:
        archive = open_archive(p, password=password)
        info = archive.get_info()
        return {
            "path": info["path"],
            "format": info["format"],
            "file_count": info["file_count"],
            "dir_count": info["dir_count"],
            "total_raw": info["total_raw"],
            "total_compressed": info["total_compressed"],
            "ratio": info["ratio"],
            "size_on_disk": info["size_on_disk"],
            "supports_password": archive.supports_password,
            "supports_volumes": archive.supports_volumes,
        }
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


# ── Test ──────────────────────────────────────────────

@app.post("/api/test")
async def api_test(request: Request):
    data = await request.json()
    path = data.get("path", "")
    password = data.get("password") or None

    p = Path(path)
    if not p.exists():
        return {"error": f"文件不存在: {path}"}

    try:
        archive = open_archive(p, password=password)
        ok, errors = archive.test_integrity()
        return {"success": ok, "errors": errors}
    except Exception as e:
        return {"success": False, "errors": [str(e)]}


# ── Convert ───────────────────────────────────────────

@app.post("/api/convert")
async def api_convert(request: Request):
    data = await request.json()
    src = data.get("src", "")
    dst = data.get("dst", "")
    src_password = data.get("src_password") or None
    dst_password = data.get("dst_password") or None

    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        return {"error": f"源文件不存在: {src}"}

    try:
        convert_archive(src_path, dst_path, src_password, dst_password)
        return {"success": True, "target": str(dst_path)}
    except Exception as e:
        return {"error": str(e)}


# ── Crack ─────────────────────────────────────────────

@app.post("/api/crack/start")
async def api_crack_start(request: Request):
    """启动破解任务"""
    data = await request.json()
    path = data.get("path", "")
    method = data.get("method", "smart")
    password = data.get("password") or None

    # 解析额外参数
    wordlist = data.get("wordlist")
    charset = data.get("charset")
    min_len = data.get("min_len", 1)
    max_len = data.get("max_len", 6)
    masks = data.get("masks", [])
    workers = data.get("workers", 4)

    p = Path(path)
    if not p.exists():
        return {"error": f"文件不存在: {path}"}

    task_id = str(uuid.uuid4())
    _task_progress[task_id] = {
        "status": "running",
        "attempts": 0,
        "total": 0,
        "current": "",
        "speed": 0,
        "found": False,
        "password": None,
    }

    # 在后台任务中运行
    asyncio.create_task(_run_crack(task_id, p, method, wordlist, charset,
                                   min_len, max_len, masks, workers))

    return {"task_id": task_id}


@app.get("/api/crack/progress/{task_id}")
async def api_crack_progress(task_id: str):
    """获取破解进度（SSE）"""
    async def event_stream():
        last_attempts = 0
        while True:
            state = _task_progress.get(task_id)
            if not state:
                yield f"data: {json.dumps({'status': 'not_found'})}\n\n"
                break

            if state["status"] == "completed" or state["status"] == "error":
                yield f"data: {json.dumps(state)}\n\n"
                break

            # 只在有新进展时才推送
            if state["attempts"] != last_attempts:
                last_attempts = state["attempts"]
                yield f"data: {json.dumps(state)}\n\n"

            await asyncio.sleep(0.2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _crack_progress_callback(task_id: str):
    """创建进度回调函数"""
    def callback(attempts: int, total: int, current: str, speed: float):
        if task_id in _task_progress:
            _task_progress[task_id].update({
                "attempts": attempts,
                "total": total,
                "current": current,
                "speed": speed,
            })
    return callback


async def _run_crack(task_id, path, method, wordlist, charset,
                     min_len, max_len, masks, workers):
    """在后台线程中运行破解"""
    try:
        cracker = PasswordCracker(path)
        cracker.callback = _crack_progress_callback(task_id)

        loop = asyncio.get_running_loop()

        def run():
            if method == "dict":
                if wordlist:
                    return cracker.dict_attack_from_file(Path(wordlist))
                return cracker.dict_attack()
            elif method == "brute":
                cs = charset or "0123456789"
                return cracker.brute_force(cs, min_len, max_len, workers)
            elif method == "mask":
                return cracker.mask_attack(masks)
            else:
                return cracker.smart_attack(workers)

        result = await loop.run_in_executor(None, run)

        _task_progress[task_id].update({
            "status": "completed",
            "found": result.found,
            "password": result.password,
            "attempts": result.attempts,
            "speed": result.speed,
            "elapsed": result.elapsed,
        })
    except Exception as e:
        _task_progress[task_id].update({
            "status": "error",
            "error": str(e),
        })


# ── Batch ─────────────────────────────────────────────

@app.post("/api/batch/extract")
async def api_batch_extract(request: Request):
    data = await request.json()
    pattern = data.get("pattern", "")
    password = data.get("password") or None

    results = batch_extract(pattern, password=password)
    return {
        "results": [
            {"src": str(s), "dst": str(d)} for s, d in results
        ]
    }


@app.post("/api/batch/test")
async def api_batch_test(request: Request):
    data = await request.json()
    pattern = data.get("pattern", "")
    password = data.get("password") or None

    results = batch_test(pattern, password=password)
    return {
        "results": [
            {"src": str(s), "ok": ok, "errors": errors}
            for s, ok, errors in results
        ]
    }


# ── 文件浏览 ──────────────────────────────────────────

@app.post("/api/browse")
async def api_browse(request: Request):
    data = await request.json()
    path = data.get("path", "")
    show_hidden = data.get("show_hidden", False)

    p = Path(path) if path else Path.cwd()
    if not p.exists():
        p = Path.cwd()
    if not p.is_dir():
        p = p.parent

    try:
        items = []
        for child in sorted(p.iterdir()):
            if not show_hidden and child.name.startswith("."):
                continue
            try:
                is_dir = child.is_dir()
                is_archive = child.suffix.lower() in (
                    ".zip", ".7z", ".rar", ".tar", ".gz", ".tar.gz"
                )
                items.append({
                    "name": child.name,
                    "path": str(child),
                    "is_dir": is_dir,
                    "is_archive": is_archive and not is_dir,
                    "size": child.stat().st_size if not is_dir else 0,
                })
            except OSError:
                continue

        return {
            "current": str(p),
            "parent": str(p.parent) if p.parent != p else None,
            "items": items,
        }
    except Exception as e:
        return {"error": str(e), "current": str(p), "items": []}


# ── 工具函数 ──────────────────────────────────────────

def _parse_volume(volume_str) -> Optional[int]:
    if volume_str is None:
        return None
    volume_str = str(volume_str).upper().strip()
    if volume_str.endswith("G"):
        return int(float(volume_str[:-1]) * 1024 ** 3)
    if volume_str.endswith("M"):
        return int(float(volume_str[:-1]) * 1024 ** 2)
    if volume_str.endswith("K"):
        return int(float(volume_str[:-1]) * 1024)
    try:
        return int(volume_str)
    except ValueError:
        return None
