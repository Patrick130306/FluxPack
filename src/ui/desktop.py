"""FluxPack 桌面 GUI —— CustomTkinter 原生应用"""

import os
import sys
import time
import threading
import queue
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

# 导入核心模块
from src.core.formats import open_archive, detect_format
from src.core.cracker import PasswordCracker
from src.core.operations import convert_archive, batch_test
from src.core.advanced import (
    diff_archives, repair_archive, find_duplicates,
    checksum_file, generate_checksum, verify_checksum, save_checksums,
    preview_file_in_archive, smart_cleanup, merge_archives,
    DuplicateGroup, DiffResult,
    # 新功能:
    smart_password_candidates, recommend_format, auto_classify,
    steganography_check, encryption_rating,
    replace_in_archive, delete_from_archive,
    fulltext_search_archives, recursive_extract,
    health_report, space_waste_analysis, compatibility_check,
    intelligent_splitting, list_media_presets,
    url_to_archive, auto_clean_extract,
    get_templates, apply_template,
    incremental_backup, TimeMachine,
)
from src.core.hybrid import (
    hybrid_compress, image_optimized_pack, Pipeline,
    analyze_files, classify_file, _fmt_size as hfmt,
)
from src.core.power import (
    install_context_menu, uninstall_context_menu, check_context_menu,
    format_battle,
    batch_password_unlock, unlock_with_smart_candidates,
)
from src.core.phi import (
    dms_check, dms_signin, create_self_extracting_html,
    score_archive, diff_archives_visual,
)
from src.core.omega import (
    check_zip_bomb, estimate_crack_time, build_archive_index, save_index, load_index,
    search_archive_index, get_savings_summary, record_compression, suggest_organization,
    create_honeypot, check_honeypot_log,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── 现代化配色方案 ──────────────────────────
# 灵感: Linear / Vercel / Stripe 风格
THEME = {
    "bg": "#0c0e12",          # 更深的主体背景
    "bg2": "#14171c",         # 面板背景
    "bg3": "#1c2028",         # 输入框/按钮背景
    "bg4": "#242830",         # hover 状态
    "border": "#2a2f38",      # 边框
    "text": "#e8ecf0",        # 主文字
    "text2": "#7a8494",       # 次要文字
    "text3": "#4a5464",       # 禁用文字
    "accent": "#3b82f6",      # 蓝色主色调 (更像 Tailwind blue-500)
    "accent2": "#2563eb",     # 深蓝 (blue-600)
    "accent3": "#1e3a5f",     # 暗蓝背景
    "green": "#22c55e",       # Tailwind green-500
    "red": "#ef4444",         # Tailwind red-500
    "yellow": "#f59e0b",      # Tailwind amber-500
    "orange": "#f97316",      # Tailwind orange-500
    "purple": "#a855f7",      # Tailwind purple-500
    "radius": 10,             # 全局圆角
    "radius_sm": 6,           # 小圆角
    "radius_lg": 16,          # 大圆角
    "radius_xl": 24,          # 超大圆角 (胶囊按钮)
}

# ── 全局 CTk 主题覆盖 ─────────────────────
ctk.ThemeManager.theme["CTkFrame"]["corner_radius"] = THEME["radius"]
ctk.ThemeManager.theme["CTkFrame"]["fg_color"] = ["#f0f2f5", THEME["bg2"]]
ctk.ThemeManager.theme["CTkFrame"]["border_color"] = ["#e2e5ea", THEME["border"]]

ctk.ThemeManager.theme["CTkButton"]["corner_radius"] = THEME["radius"]
ctk.ThemeManager.theme["CTkButton"]["fg_color"] = ["#2563eb", THEME["accent2"]]
ctk.ThemeManager.theme["CTkButton"]["hover_color"] = ["#1d4ed8", THEME["accent"]]
ctk.ThemeManager.theme["CTkButton"]["text_color"] = ["#ffffff", "#ffffff"]
ctk.ThemeManager.theme["CTkButton"]["border_width"] = 0

ctk.ThemeManager.theme["CTkEntry"]["corner_radius"] = THEME["radius_sm"]
ctk.ThemeManager.theme["CTkEntry"]["fg_color"] = ["#ffffff", THEME["bg3"]]
ctk.ThemeManager.theme["CTkEntry"]["border_color"] = ["#d4d8dd", THEME["border"]]
ctk.ThemeManager.theme["CTkEntry"]["text_color"] = ["#1a1d23", THEME["text"]]
ctk.ThemeManager.theme["CTkEntry"]["placeholder_text_color"] = ["#9ca3af", THEME["text2"]]

ctk.ThemeManager.theme["CTkTextbox"]["corner_radius"] = THEME["radius_sm"]
ctk.ThemeManager.theme["CTkTextbox"]["fg_color"] = ["#f8f9fc", THEME["bg"]]
ctk.ThemeManager.theme["CTkTextbox"]["text_color"] = ["#1a1d23", THEME["text"]]

ctk.ThemeManager.theme["CTkLabel"]["text_color"] = ["#1a1d23", THEME["text"]]

ctk.ThemeManager.theme["CTkProgressBar"]["corner_radius"] = THEME["radius_xl"]
ctk.ThemeManager.theme["CTkProgressBar"]["fg_color"] = ["#e8ecf0", THEME["bg3"]]
ctk.ThemeManager.theme["CTkProgressBar"]["progress_color"] = ["#2563eb", THEME["accent"]]
ctk.ThemeManager.theme["CTkProgressBar"]["border_width"] = 0

ctk.ThemeManager.theme["CTkSwitch"]["corner_radius"] = THEME["radius_xl"]
ctk.ThemeManager.theme["CTkSwitch"]["progress_color"] = ["#2563eb", THEME["accent"]]

ctk.ThemeManager.theme["CTkOptionMenu"]["corner_radius"] = THEME["radius_sm"]
ctk.ThemeManager.theme["CTkOptionMenu"]["fg_color"] = ["#ffffff", THEME["bg3"]]
ctk.ThemeManager.theme["CTkOptionMenu"]["button_color"] = ["#e8ecf0", THEME["bg4"]]
ctk.ThemeManager.theme["CTkOptionMenu"]["text_color"] = ["#1a1d23", THEME["text"]]

APP_TITLE = "FluxPack"
APP_VERSION = "0.2.0"
WINDOW_SIZE = "1100x720"


# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════

def fmt_size(size: Optional[int]) -> str:
    if size is None: return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"


def run_in_thread(target, callback=None, error_callback=None):
    """在后台线程运行任务，完成后回调主线程"""
    q = queue.Queue()

    def worker():
        try:
            result = target()
            q.put(("ok", result))
        except Exception as e:
            q.put(("error", e))

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def poll():
        try:
            status, data = q.get_nowait()
            if status == "ok":
                if callback:
                    callback(data)
            else:
                if error_callback:
                    error_callback(data)
                else:
                    messagebox.showerror("错误", str(data))
        except queue.Empty:
            root.after(100, poll)

    root.after(100, poll)
    return t


# ═══════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════

class FluxPackApp(ctk.CTk):
    """FluxPack 桌面主窗口"""

    def __init__(self):
        super().__init__()

        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.geometry(WINDOW_SIZE)
        self.minsize(900, 600)

        # 左上角图标区域——用 Label 模拟
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── 顶栏 ────────────────────────────────────
        self.topbar = ctk.CTkFrame(self, height=44, corner_radius=0, fg_color=THEME["bg"])
        self.topbar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self.topbar.grid_columnconfigure(0, weight=1)

        # 左侧标志
        logo_frame = ctk.CTkFrame(self.topbar, fg_color="transparent")
        logo_frame.grid(row=0, column=0, padx=(14, 0), pady=6, sticky="w")

        self.title_label = ctk.CTkLabel(
            logo_frame, text="◆", font=ctk.CTkFont(size=14),
            text_color=THEME["accent"], anchor="w",
        )
        self.title_label.pack(side="left")

        ctk.CTkLabel(
            logo_frame, text="FluxPack",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text"], anchor="w",
        ).pack(side="left", padx=(5, 0))

        # 状态指示
        self.status_label = ctk.CTkLabel(
            self.topbar, text="● 就绪",
            font=ctk.CTkFont(size=10),
            text_color=THEME["green"], anchor="e",
        )
        self.status_label.grid(row=0, column=1, padx=10, sticky="e")

        # 暗色/亮色开关
        self.mode_switch = ctk.CTkSwitch(
            self.topbar, text="", width=28,
            command=self._toggle_theme,
            onvalue="dark", offvalue="light",
            progress_color=THEME["accent"],
        )
        self.mode_switch.grid(row=0, column=2, padx=(0, 14), pady=6, sticky="e")
        self.mode_switch.select()

        # ── 标签页 ──────────────────────────────────
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 创建各标签页
        self.tab_compress = self.tabview.add("📦 压缩")
        self.tab_extract = self.tabview.add("📂 解压")
        self.tab_browse = self.tabview.add("📋 浏览")
        self.tab_crack = self.tabview.add("🔓 破解")
        self.tab_convert = self.tabview.add("🔄 转换")
        self.tab_test = self.tabview.add("✅ 校验")
        # ── 高级功能标签页 ──
        self.tab_diff = self.tabview.add("🆚 对比")
        self.tab_repair = self.tabview.add("🔧 修复")
        self.tab_cleanup = self.tabview.add("🧹 清理")
        self.tab_analysis = self.tabview.add("📊 分析")
        self.tab_ai = self.tabview.add("🔮 智能")
        self.tab_scan = self.tabview.add("🔍 扫描")
        self.tab_edit = self.tabview.add("✏️ 编辑")
        self.tab_hybrid = self.tabview.add("🧬 混合")
        self.tab_pipeline = self.tabview.add("🔧 管道")
        self.tab_integrate = self.tabview.add("🖱 集成")

        # 初始化各页面
        self._init_compress_tab()
        self._init_extract_tab()
        self._init_browse_tab()
        self._init_crack_tab()
        self._init_convert_tab()
        self._init_test_tab()
        self._init_diff_tab()
        self._init_repair_tab()
        self._init_cleanup_tab()
        self._init_analysis_tab()
        self._init_ai_tab()
        self._init_scan_tab()
        self._init_edit_tab()
        self._init_hybrid_tab()
        self._init_pipeline_tab()
        self._init_integrate_tab()

    def _toggle_theme(self):
        mode = self.mode_switch.get()
        ctk.set_appearance_mode(mode)

    def set_status(self, text: str):
        dot = "●" if "就绪" in text or "完成" in text or "成功" in text else "○"
        self.status_label.configure(text=f"{dot} {text}")
        self.update_idletasks()

    def log(self, widget: ctk.CTkTextbox, text: str, tag: str = None):
        """向输出框追加日志"""
        widget.configure(state="normal")
        widget.insert("end", text + "\n", tag)
        widget.see("end")
        widget.configure(state="disabled")


    # ══════════════════════════════════════════════════
    # 压缩页面
    # ══════════════════════════════════════════════════

    def _init_compress_tab(self):
        tab = self.tab_compress
        tab.grid_columnconfigure(0, weight=1)

        # 源文件
        ctk.CTkLabel(tab, text="源文件/文件夹：", anchor="w").grid(row=0, column=0, sticky="w", pady=(12, 2), padx=12)
        row1 = ctk.CTkFrame(tab, fg_color="transparent")
        row1.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        row1.grid_columnconfigure(0, weight=1)
        self.cmp_src_var = ctk.StringVar()
        ctk.CTkEntry(row1, textvariable=self.cmp_src_var, placeholder_text="文件/文件夹路径（多个用 ; 分隔）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row1, text="浏览文件", width=90, command=lambda: self._add_src_file()).grid(row=0, column=1, padx=2)
        ctk.CTkButton(row1, text="浏览文件夹", width=90, command=lambda: self._add_src_dir()).grid(row=0, column=2)
        # 已选文件列表
        self.cmp_file_list = ctk.CTkTextbox(tab, height=60, state="disabled")
        self.cmp_file_list.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 6))

        # 输出路径
        ctk.CTkLabel(tab, text="输出路径：", anchor="w").grid(row=3, column=0, sticky="w", padx=12)
        row3 = ctk.CTkFrame(tab, fg_color="transparent")
        row3.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
        row3.grid_columnconfigure(0, weight=1)
        self.cmp_out_var = ctk.StringVar()
        ctk.CTkEntry(row3, textvariable=self.cmp_out_var, placeholder_text="如: D:/archive.7z").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row3, text="另存为", width=90, command=self._choose_output).grid(row=0, column=1)

        # 选项
        opt_frame = ctk.CTkFrame(tab)
        opt_frame.grid(row=5, column=0, sticky="ew", padx=12, pady=6)
        opt_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(opt_frame, text="格式：").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.cmp_fmt_var = ctk.StringVar(value="7z")
        fmt_menu = ctk.CTkOptionMenu(opt_frame, variable=self.cmp_fmt_var, values=["7z", "zip", "tar.gz", "tar"])
        fmt_menu.grid(row=0, column=0, padx=(50, 6), pady=4, sticky="w")

        ctk.CTkLabel(opt_frame, text="密码：").grid(row=0, column=1, padx=6, pady=4, sticky="w")
        self.cmp_pwd_var = ctk.StringVar()
        ctk.CTkEntry(opt_frame, textvariable=self.cmp_pwd_var, placeholder_text="留空不加密", show="*", width=150).grid(row=0, column=1, padx=(40, 6), pady=4, sticky="w")

        ctk.CTkLabel(opt_frame, text="分卷：").grid(row=0, column=2, padx=6, pady=4, sticky="w")
        self.cmp_vol_var = ctk.StringVar()
        ctk.CTkEntry(opt_frame, textvariable=self.cmp_vol_var, placeholder_text="如: 10M, 1G", width=120).grid(row=0, column=2, padx=(40, 6), pady=4, sticky="w")

        # 按钮
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=6, column=0, pady=8)
        self.cmp_btn = ctk.CTkButton(btn_frame, text="⚡ 开始压缩", width=200, height=36,
                                       command=self._do_compress, fg_color="#1f6feb")
        self.cmp_btn.pack()

        # 进度
        self.cmp_progress = ctk.CTkProgressBar(tab, mode="indeterminate")
        self.cmp_progress.grid(row=7, column=0, sticky="ew", padx=12, pady=(4, 0))

        # 日志
        self.cmp_log = ctk.CTkTextbox(tab, height=100, state="disabled")
        self.cmp_log.grid(row=8, column=0, sticky="ew", padx=12, pady=(6, 8))

        self._cmp_sources = []

    def _add_src_file(self):
        files = filedialog.askopenfilenames(title="选择要压缩的文件")
        for f in files:
            if f not in self._cmp_sources:
                self._cmp_sources.append(f)
        self._update_src_list()

    def _add_src_dir(self):
        d = filedialog.askdirectory(title="选择要压缩的文件夹")
        if d and d not in self._cmp_sources:
            self._cmp_sources.append(d)
        self._update_src_list()

    def _update_src_list(self):
        self.cmp_file_list.configure(state="normal")
        self.cmp_file_list.delete("1.0", "end")
        for s in self._cmp_sources:
            self.cmp_file_list.insert("end", f"📄 {s}\n")
        self.cmp_file_list.configure(state="disabled")
        self.cmp_src_var.set("; ".join(self._cmp_sources))

    def _choose_output(self):
        f = filedialog.asksaveasfilename(
            title="选择输出路径",
            defaultextension=".7z",
            filetypes=[
                ("7Z 压缩包", "*.7z"),
                ("ZIP 压缩包", "*.zip"),
                ("TAR.GZ 压缩包", "*.tar.gz"),
                ("所有文件", "*.*"),
            ],
        )
        if f:
            self.cmp_out_var.set(f)

    def _do_compress(self):
        if not self._cmp_sources:
            messagebox.showwarning("警告", "请先选择源文件")
            return
        output = self.cmp_out_var.get()
        if not output:
            messagebox.showwarning("警告", "请选择输出路径")
            return

        password = self.cmp_pwd_var.get() or None
        volume = self.cmp_vol_var.get() or None

        self.cmp_btn.configure(state="disabled", text="压缩中...")
        self.cmp_progress.start()
        self.set_status("压缩中...")
        self.log(self.cmp_log, f"📦 开始压缩 {len(self._cmp_sources)} 个路径 → {output}")

        sources = [Path(s) for s in self._cmp_sources]

        def task():
            out = Path(output)
            try:
                fmt = detect_format(out)
            except ValueError:
                out = out.with_suffix(".7z")
            archive = open_archive(out, password=password)
            return archive.compress(sources, volume_size=self._parse_vol(volume))

        def callback(results):
            self.cmp_progress.stop()
            self.cmp_progress.set(1)
            self.cmp_btn.configure(state="normal", text="⚡ 开始压缩")
            self.set_status("就绪")
            if len(results) > 1:
                self.log(self.cmp_log, f"✅ 创建了 {len(results)} 个分卷:")
                for r in results:
                    self.log(self.cmp_log, f"   📦 {r.name} ({fmt_size(r.stat().st_size)})")
            else:
                self.log(self.cmp_log, f"✅ 压缩完成: {results[0]} ({fmt_size(results[0].stat().st_size)})")

        def err_callback(e):
            self.cmp_progress.stop()
            self.cmp_btn.configure(state="normal", text="⚡ 开始压缩")
            self.set_status("就绪")
            self.log(self.cmp_log, f"❌ 错误: {e}")

        run_in_thread(task, callback, err_callback)

    @staticmethod
    def _parse_vol(s):
        if not s: return None
        s = s.upper().strip()
        if s.endswith("G"): return int(float(s[:-1]) * 1024**3)
        if s.endswith("M"): return int(float(s[:-1]) * 1024**2)
        if s.endswith("K"): return int(float(s[:-1]) * 1024)
        try: return int(s)
        except: return None

    # ══════════════════════════════════════════════════
    # 解压页面
    # ══════════════════════════════════════════════════

    def _init_extract_tab(self):
        tab = self.tab_extract
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="压缩包路径：", anchor="w").grid(row=0, column=0, sticky="w", pady=(12, 2), padx=12)
        row0 = ctk.CTkFrame(tab, fg_color="transparent")
        row0.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        row0.grid_columnconfigure(0, weight=1)
        self.ext_path_var = ctk.StringVar()
        ctk.CTkEntry(row0, textvariable=self.ext_path_var, placeholder_text="选择要解压的压缩包").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row0, text="浏览", width=90, command=lambda: self._browse_ext()).grid(row=0, column=1)

        opt_frame = ctk.CTkFrame(tab)
        opt_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        opt_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(opt_frame, text="密码（可选）：").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.ext_pwd_var = ctk.StringVar()
        ctk.CTkEntry(opt_frame, textvariable=self.ext_pwd_var, placeholder_text="没密码则留空", show="*", width=180).grid(row=0, column=0, padx=(100, 6), pady=4, sticky="w")

        ctk.CTkLabel(opt_frame, text="输出目录（可选）：").grid(row=0, column=1, padx=6, pady=4, sticky="w")
        self.ext_dir_var = ctk.StringVar()
        ctk.CTkEntry(opt_frame, textvariable=self.ext_dir_var, placeholder_text="默认: 同目录下同名文件夹", width=220).grid(row=0, column=1, padx=(120, 6), pady=4, sticky="w")

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=3, column=0, pady=8)
        self.ext_btn = ctk.CTkButton(btn_frame, text="📂 开始解压", width=200, height=36,
                                       command=self._do_extract, fg_color="#1f6feb")
        self.ext_btn.pack()

        self.ext_progress = ctk.CTkProgressBar(tab, mode="indeterminate")
        self.ext_progress.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 0))

        self.ext_log = ctk.CTkTextbox(tab, height=150, state="disabled")
        self.ext_log.grid(row=5, column=0, sticky="ew", padx=12, pady=(6, 8))

        # 底部快速操作按钮
        info_frame = ctk.CTkFrame(tab, fg_color="transparent")
        info_frame.grid(row=6, column=0, pady=4)
        ctk.CTkButton(info_frame, text="查看压缩包内容", command=self._ext_show_info).pack(side="left", padx=4)
        ctk.CTkButton(info_frame, text="校验完整性", command=self._ext_do_test).pack(side="left", padx=4)

    def _browse_ext(self):
        f = filedialog.askopenfilename(
            title="选择压缩包",
            filetypes=[
                ("压缩包", "*.zip *.7z *.rar *.tar *.tar.gz"),
                ("所有文件", "*.*"),
            ],
        )
        if f:
            self.ext_path_var.set(f)

    def _do_extract(self):
        path = self.ext_path_var.get()
        if not path:
            messagebox.showwarning("警告", "请选择压缩包")
            return

        password = self.ext_pwd_var.get() or None
        target = self.ext_dir_var.get() or ""

        self.ext_btn.configure(state="disabled", text="解压中...")
        self.ext_progress.start()
        self.set_status("解压中...")
        self.log(self.ext_log, f"📂 解压: {path}")

        def task():
            p = Path(path)
            dst = Path(target) if target else p.parent / p.stem
            dst.mkdir(parents=True, exist_ok=True)
            archive = open_archive(p, password=password)
            archive.extract(dst)
            return dst

        def callback(dst):
            self.ext_progress.stop()
            self.ext_progress.set(1)
            self.ext_btn.configure(state="normal", text="📂 开始解压")
            self.set_status("就绪")
            self.log(self.ext_log, f"✅ 已解压到: {dst}")

        def err_callback(e):
            self.ext_progress.stop()
            self.ext_btn.configure(state="normal", text="📂 开始解压")
            self.set_status("就绪")
            self.log(self.ext_log, f"❌ {e}")

        run_in_thread(task, callback, err_callback)

    def _ext_show_info(self):
        path = self.ext_path_var.get()
        if not path: return
        password = self.ext_pwd_var.get() or None
        self.tabview.set("📋 浏览")
        self.brs_path_var.set(path)
        self.brs_pwd_var.set(password or "")
        self._do_browse()

    def _ext_do_test(self):
        path = self.ext_path_var.get()
        if not path: return
        password = self.ext_pwd_var.get() or None
        self.tabview.set("✅ 校验")
        self.tst_path_var.set(path)
        self.tst_pwd_var.set(password or "")
        self._do_test()

    # ══════════════════════════════════════════════════
    # 浏览页面
    # ══════════════════════════════════════════════════

    def _init_browse_tab(self):
        tab = self.tab_browse
        tab.grid_columnconfigure(0, weight=1)

        row0 = ctk.CTkFrame(tab, fg_color="transparent")
        row0.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        row0.grid_columnconfigure(0, weight=1)
        self.brs_path_var = ctk.StringVar()
        ctk.CTkEntry(row0, textvariable=self.brs_path_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row0, text="浏览", width=80, command=self._brs_browse).grid(row=0, column=1, padx=2)
        self.brs_pwd_var = ctk.StringVar()
        ctk.CTkEntry(row0, textvariable=self.brs_pwd_var, placeholder_text="密码", show="*", width=120).grid(row=0, column=2, padx=2)
        ctk.CTkButton(row0, text="📋 查看", width=100, command=self._do_browse, fg_color="#1f6feb").grid(row=0, column=3, padx=(2, 0))

        # 文件列表
        col_frame = ctk.CTkFrame(tab)
        col_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        col_frame.grid_columnconfigure(0, weight=1)
        col_frame.grid_rowconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        self.brs_table = ctk.CTkTextbox(col_frame, state="disabled", font=ctk.CTkFont(size=12))
        self.brs_table.grid(row=0, column=0, sticky="nsew")

        # 底部信息
        self.brs_info = ctk.CTkLabel(tab, text="", anchor="w", font=ctk.CTkFont(size=12))
        self.brs_info.grid(row=2, column=0, sticky="ew", padx=12, pady=4)

    def _brs_browse(self):
        f = filedialog.askopenfilename(title="选择压缩包")
        if f:
            self.brs_path_var.set(f)

    def _do_browse(self):
        path = self.brs_path_var.get()
        if not path: return
        password = self.brs_pwd_var.get() or None

        def task():
            archive = open_archive(Path(path), password=password)
            return archive.get_info()

        def callback(info):
            self.brs_table.configure(state="normal")
            self.brs_table.delete("1.0", "end")
            self.brs_table.insert("end",
                f"📦 {Path(path).name}\n"
                f"{'='*50}\n"
                f"格式: {info['format']}\n"
                f"大小: {fmt_size(info['size_on_disk'])}\n"
                f"原始大小: {fmt_size(info['total_raw'])}\n"
                f"压缩后: {fmt_size(info['total_compressed'])}\n"
                f"压缩率: {info['ratio']:.1f}%\n"
                f"文件数: {info['file_count']:,}   目录数: {info['dir_count']:,}\n"
                f"{'='*50}\n\n"
            )
            # 文件列表
            for e in info['entries']:
                icon = "📁" if e.is_dir else "📄"
                ratio = f"({e.ratio*100:.1f}%)" if e.ratio else ""
                self.brs_table.insert("end",
                    f"{icon} {e.name:<50} {fmt_size(e.size):>8} {ratio}\n"
                )
            self.brs_table.configure(state="disabled")
            self.brs_info.configure(
                text=f"格式: {info['format']}  |  文件: {info['file_count']}  |  "
                     f"原始: {fmt_size(info['total_raw'])}  →  "
                     f"压缩: {fmt_size(info['total_compressed'])}  "
                     f"({info['ratio']:.1f}%)"
            )

        run_in_thread(task, callback)

    # ══════════════════════════════════════════════════
    # 破解页面
    # ══════════════════════════════════════════════════

    def _init_crack_tab(self):
        tab = self.tab_crack
        tab.grid_columnconfigure(0, weight=1)

        row0 = ctk.CTkFrame(tab, fg_color="transparent")
        row0.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        row0.grid_columnconfigure(0, weight=1)
        self.crk_path_var = ctk.StringVar()
        ctk.CTkEntry(row0, textvariable=self.crk_path_var, placeholder_text="加密压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row0, text="浏览", width=80, command=lambda: self._browse_path(self.crk_path_var)).grid(row=0, column=1)

        # 方法选择
        method_frame = ctk.CTkFrame(tab)
        method_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        method_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(method_frame, text="破解方法：").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.crk_method_var = ctk.StringVar(value="smart")
        method_menu = ctk.CTkOptionMenu(method_frame, variable=self.crk_method_var,
            values=["smart (推荐)", "dict", "brute", "mask"],
            command=self._on_crack_method_change)
        method_menu.grid(row=0, column=0, padx=(80, 6), pady=6, sticky="w")

        ctk.CTkLabel(method_frame, text="字典文件：").grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self.crk_dict_var = ctk.StringVar()
        dict_entry = ctk.CTkEntry(method_frame, textvariable=self.crk_dict_var, placeholder_text="留空=内置字典")
        dict_entry.grid(row=0, column=1, padx=(70, 6), pady=6, sticky="ew")

        ctk.CTkLabel(method_frame, text="线程数：").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        self.crk_workers_var = ctk.StringVar(value="4")
        workers_entry = ctk.CTkEntry(method_frame, textvariable=self.crk_workers_var, width=60)
        workers_entry.grid(row=0, column=2, padx=(60, 6), pady=6, sticky="w")

        # 高级选项（暴力/掩码用）
        self.crk_adv_frame = ctk.CTkFrame(tab)
        self.crk_adv_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        self.crk_adv_frame.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkLabel(self.crk_adv_frame, text="字符集：").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.crk_charset_var = ctk.StringVar(value="0123456789")
        ctk.CTkEntry(self.crk_adv_frame, textvariable=self.crk_charset_var).grid(row=0, column=0, padx=(60, 6), pady=4, sticky="ew")

        ctk.CTkLabel(self.crk_adv_frame, text="掩码：").grid(row=0, column=1, padx=6, pady=4, sticky="w")
        self.crk_mask_var = ctk.StringVar()
        ctk.CTkEntry(self.crk_adv_frame, textvariable=self.crk_mask_var, placeholder_text="?l?l?d?d").grid(row=0, column=1, padx=(50, 6), pady=4, sticky="ew")

        mask_info = ctk.CTkFrame(self.crk_adv_frame, fg_color="transparent")
        mask_info.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 4))
        ctk.CTkLabel(mask_info, text="?l=小写  ?u=大写  ?d=数字  ?s=特殊  ?a=所有", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")

        # 长度
        len_frame = ctk.CTkFrame(self.crk_adv_frame, fg_color="transparent")
        len_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
        ctk.CTkLabel(len_frame, text="最小长度：").pack(side="left")
        self.crk_minlen_var = ctk.StringVar(value="1")
        ctk.CTkEntry(len_frame, textvariable=self.crk_minlen_var, width=60).pack(side="left", padx=(6, 20))
        ctk.CTkLabel(len_frame, text="最大长度：").pack(side="left")
        self.crk_maxlen_var = ctk.StringVar(value="6")
        ctk.CTkEntry(len_frame, textvariable=self.crk_maxlen_var, width=60).pack(side="left", padx=(6, 0))

        self.crk_adv_frame.grid_remove()  # 初始隐藏

        # 按钮
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=3, column=0, pady=8)
        self.crk_btn = ctk.CTkButton(btn_frame, text="🔓 开始破解", width=200, height=36,
                                       command=self._do_crack, fg_color="#da3633")
        self.crk_btn.pack(side="left", padx=4)
        self.crk_stop_btn = ctk.CTkButton(btn_frame, text="⏹ 停止", width=80, state="disabled", command=self._stop_crack)
        self.crk_stop_btn.pack(side="left", padx=4)

        # 进度
        self.crk_progress = ctk.CTkProgressBar(tab)
        self.crk_progress.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 0))
        self.crk_progress.set(0)
        self.crk_prog_label = ctk.CTkLabel(tab, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.crk_prog_label.grid(row=5, column=0, sticky="ew", padx=12, pady=(2, 0))

        # 日志
        self.crk_log = ctk.CTkTextbox(tab, height=160, state="disabled")
        self.crk_log.grid(row=6, column=0, sticky="ew", padx=12, pady=(6, 8))
        tab.grid_rowconfigure(6, weight=1)

        self._crack_running = False
        self._crack_thread = None
        self._crack_stop_flag = False

    def _on_crack_method_change(self, method):
        if method in ("brute", "mask"):
            self.crk_adv_frame.grid()
        else:
            self.crk_adv_frame.grid_remove()

    def _do_crack(self):
        path = self.crk_path_var.get()
        if not path:
            messagebox.showwarning("警告", "请选择压缩包")
            return

        self._crack_running = True
        self._crack_stop_flag = False
        self.crk_btn.configure(state="disabled", text="破解中...")
        self.crk_stop_btn.configure(state="normal")
        self.crk_progress.set(0)
        self.crk_prog_label.configure(text="⏳ 初始化...")
        self.set_status("密码破解中...")
        self.log(self.crk_log, f"🔓 开始破解: {path}")

        method = self.crk_method_var.get().split()[0]  # "smart (推荐)" → "smart"
        p = Path(path)

        def task():
            cracker = PasswordCracker(p)
            total_attempts = [0]
            last_update = [0]

            def progress_cb(attempts, total, current, speed):
                total_attempts[0] = attempts
                # 更新进度到 UI
                def update():
                    pct = (attempts / total * 100) if total > 0 else 0
                    self.crk_progress.set(min(pct / 100, 0.99))
                    self.crk_prog_label.configure(
                        text=f"🔍 尝试: {attempts:,}  |  当前: {current}  |  {speed:.0f} pwd/s"
                    )
                    self.update_idletasks()
                root.after(0, update)

            cracker.callback = progress_cb

            if method == "dict":
                wl = self.crk_dict_var.get() or None
                if wl:
                    return cracker.dict_attack_from_file(Path(wl))
                return cracker.dict_attack()
            elif method == "brute":
                cs = self.crk_charset_var.get() or "0123456789"
                min_len = int(self.crk_minlen_var.get() or 1)
                max_len = int(self.crk_maxlen_var.get() or 6)
                workers = int(self.crk_workers_var.get() or 4)
                return cracker.brute_force(cs, min_len, max_len, workers)
            elif method == "mask":
                masks = [m.strip() for m in self.crk_mask_var.get().split(",") if m.strip()]
                return cracker.mask_attack(masks)
            else:
                workers = int(self.crk_workers_var.get() or 4)
                return cracker.smart_attack(workers)

        def callback(result):
            self._crack_running = False
            self.crk_btn.configure(state="normal", text="🔓 开始破解")
            self.crk_stop_btn.configure(state="disabled")
            self.set_status("就绪")
            self.crk_progress.set(1)
            self.crk_prog_label.configure(text="完成")
            self.log(self.crk_log, result.summary)

        def err_callback(e):
            self._crack_running = False
            self.crk_btn.configure(state="normal", text="🔓 开始破解")
            self.crk_stop_btn.configure(state="disabled")
            self.set_status("就绪")
            self.log(self.crk_log, f"❌ 错误: {e}")

        run_in_thread(task, callback, err_callback)

    def _stop_crack(self):
        self._crack_running = False
        self._crack_stop_flag = True
        self.crk_btn.configure(state="normal", text="🔓 开始破解")
        self.crk_stop_btn.configure(state="disabled")
        self.crk_prog_label.configure(text="⏹ 已停止")
        self.log(self.crk_log, "⏹ 破解已停止")

    # ══════════════════════════════════════════════════
    # 转换页面
    # ══════════════════════════════════════════════════

    def _init_convert_tab(self):
        tab = self.tab_convert
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="源文件：", anchor="w").grid(row=0, column=0, sticky="w", pady=(12, 2), padx=12)
        row0 = ctk.CTkFrame(tab, fg_color="transparent")
        row0.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        row0.grid_columnconfigure(0, weight=1)
        self.cv_src_var = ctk.StringVar()
        ctk.CTkEntry(row0, textvariable=self.cv_src_var, placeholder_text="源压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row0, text="浏览", width=80, command=lambda: self._browse_path(self.cv_src_var)).grid(row=0, column=1)

        ctk.CTkLabel(tab, text="目标文件：", anchor="w").grid(row=2, column=0, sticky="w", padx=12)
        row1 = ctk.CTkFrame(tab, fg_color="transparent")
        row1.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))
        row1.grid_columnconfigure(0, weight=1)
        self.cv_dst_var = ctk.StringVar()
        ctk.CTkEntry(row1, textvariable=self.cv_dst_var, placeholder_text="如: output.7z").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row1, text="另存为", width=80, command=self._cv_choose_dst).grid(row=0, column=1)

        opt_frame = ctk.CTkFrame(tab)
        opt_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=6)
        ctk.CTkLabel(opt_frame, text="源密码：").grid(row=0, column=0, padx=6, pady=4, sticky="w")
        self.cv_srcpwd_var = ctk.StringVar()
        ctk.CTkEntry(opt_frame, textvariable=self.cv_srcpwd_var, show="*", width=150).grid(row=0, column=0, padx=(60, 20), pady=4, sticky="w")
        ctk.CTkLabel(opt_frame, text="目标密码：").grid(row=0, column=1, padx=6, pady=4, sticky="w")
        self.cv_dstpwd_var = ctk.StringVar()
        ctk.CTkEntry(opt_frame, textvariable=self.cv_dstpwd_var, show="*", width=150).grid(row=0, column=1, padx=(70, 6), pady=4, sticky="w")

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=5, column=0, pady=8)
        self.cv_btn = ctk.CTkButton(btn_frame, text="🔄 开始转换", width=200, height=36,
                                      command=self._do_convert, fg_color="#1f6feb")
        self.cv_btn.pack()

        self.cv_progress = ctk.CTkProgressBar(tab, mode="indeterminate")
        self.cv_progress.grid(row=6, column=0, sticky="ew", padx=12, pady=(4, 0))

        self.cv_log = ctk.CTkTextbox(tab, height=120, state="disabled")
        self.cv_log.grid(row=7, column=0, sticky="ew", padx=12, pady=(6, 8))

    def _cv_choose_dst(self):
        f = filedialog.asksaveasfilename(title="选择目标路径")
        if f:
            self.cv_dst_var.set(f)

    def _do_convert(self):
        src = self.cv_src_var.get()
        dst = self.cv_dst_var.get()
        if not src or not dst:
            messagebox.showwarning("警告", "请填写源和目标路径")
            return

        self.cv_btn.configure(state="disabled", text="转换中...")
        self.cv_progress.start()
        self.set_status("转换中...")
        self.log(self.cv_log, f"🔄 转换: {src} → {dst}")

        def task():
            convert_archive(
                Path(src), Path(dst),
                self.cv_srcpwd_var.get() or None,
                self.cv_dstpwd_var.get() or None,
            )
            return dst

        def callback(dst):
            self.cv_progress.stop()
            self.cv_btn.configure(state="normal", text="🔄 开始转换")
            self.set_status("就绪")
            self.log(self.cv_log, f"✅ 转换完成: {dst}")

        def err_callback(e):
            self.cv_progress.stop()
            self.cv_btn.configure(state="normal", text="🔄 开始转换")
            self.set_status("就绪")
            self.log(self.cv_log, f"❌ {e}")

        run_in_thread(task, callback, err_callback)

    # ══════════════════════════════════════════════════
    # 校验页面
    # ══════════════════════════════════════════════════

    def _init_test_tab(self):
        tab = self.tab_test
        tab.grid_columnconfigure(0, weight=1)

        row0 = ctk.CTkFrame(tab, fg_color="transparent")
        row0.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        row0.grid_columnconfigure(0, weight=1)
        self.tst_path_var = ctk.StringVar()
        ctk.CTkEntry(row0, textvariable=self.tst_path_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row0, text="浏览", width=80, command=lambda: self._browse_path(self.tst_path_var)).grid(row=0, column=1, padx=2)
        self.tst_pwd_var = ctk.StringVar()
        ctk.CTkEntry(row0, textvariable=self.tst_pwd_var, placeholder_text="密码", show="*", width=120).grid(row=0, column=2, padx=2)
        ctk.CTkButton(row0, text="✅ 校验", width=100, command=self._do_test, fg_color="#1f6feb").grid(row=0, column=3, padx=2)

        self.tst_result = ctk.CTkLabel(tab, text="", font=ctk.CTkFont(size=14))
        self.tst_result.grid(row=1, column=0, sticky="ew", padx=12, pady=4)

        self.tst_log = ctk.CTkTextbox(tab, height=100, state="disabled")
        self.tst_log.grid(row=2, column=0, sticky="ew", padx=12, pady=4)

        # 批量校验
        sep = ctk.CTkFrame(tab, height=2, fg_color="gray20")
        sep.grid(row=3, column=0, sticky="ew", padx=12, pady=(16, 4))

        ctk.CTkLabel(tab, text="批量校验", font=ctk.CTkFont(size=15, weight="bold")).grid(row=4, column=0, sticky="w", padx=12, pady=4)

        row5 = ctk.CTkFrame(tab, fg_color="transparent")
        row5.grid(row=5, column=0, sticky="ew", padx=12, pady=4)
        row5.grid_columnconfigure(0, weight=1)
        self.tst_batch_var = ctk.StringVar()
        ctk.CTkEntry(row5, textvariable=self.tst_batch_var, placeholder_text="通配符，如: D:/archives/*.7z").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row5, text="批量校验", width=100, command=self._do_batch_test).grid(row=0, column=1)

        self.tst_batch_log = ctk.CTkTextbox(tab, height=120, state="disabled")
        self.tst_batch_log.grid(row=6, column=0, sticky="ew", padx=12, pady=(6, 8))

    def _do_test(self):
        path = self.tst_path_var.get()
        if not path: return
        password = self.tst_pwd_var.get() or None

        def task():
            archive = open_archive(Path(path), password=password)
            return archive.test_integrity()

        def callback(result):
            ok, errors = result
            if ok:
                self.tst_result.configure(text="✅ 完整性校验通过", text_color="#3fb950")
                self.log(self.tst_log, f"✅ {Path(path).name} 完整性校验通过")
            else:
                self.tst_result.configure(text="❌ 校验失败", text_color="#f85149")
                for e in errors[:5]:
                    self.log(self.tst_log, f"  ❌ {e}")

        run_in_thread(task, callback)

    def _do_batch_test(self):
        pattern = self.tst_batch_var.get()
        if not pattern: return

        self.log(self.tst_batch_log, f"🔍 批量校验: {pattern}")

        def task():
            return batch_test(pattern)

        def callback(results):
            passed = sum(1 for _, ok, _ in results if ok)
            self.log(self.tst_batch_log, f"📊 结果: {passed}/{len(results)} 通过")
            for src, ok, errors in results:
                status = "✅" if ok else "❌"
                self.log(self.tst_batch_log, f"  {status} {src.name}")

        def err_callback(e):
            self.log(self.tst_batch_log, f"❌ {e}")

        run_in_thread(task, callback, err_callback)

    # ══════════════════════════════════════════════════
    # 通用辅助
    # ══════════════════════════════════════════════════

    @staticmethod
    def _browse_path(var):
        f = filedialog.askopenfilename(title="选择文件")
        if f:
            var.set(f)

    @staticmethod
    def _saveas_path(var):
        f = filedialog.asksaveasfilename(title="保存为")
        if f:
            var.set(f)

    @staticmethod
    def _browse_dir(var):
        d = filedialog.askdirectory(title="选择目录")
        if d:
            var.set(d)


    # ══════════════════════════════════════════════════
    # 🆚 对比 —— Archive Diff
    # ══════════════════════════════════════════════════

    def _init_diff_tab(self):
        tab = self.tab_diff
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="比较两个压缩包的内容差异", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        f1 = ctk.CTkFrame(tab, fg_color="transparent")
        f1.grid(row=1, column=0, sticky="ew", padx=12, pady=2)
        f1.grid_columnconfigure((0, 2), weight=1)
        ctk.CTkLabel(f1, text="压缩包 A：").grid(row=0, column=0, sticky="w")
        self.diff_a_var = ctk.StringVar()
        ctk.CTkEntry(f1, textvariable=self.diff_a_var).grid(row=0, column=0, padx=(80, 4), sticky="ew")
        ctk.CTkButton(f1, text="浏览", width=70, command=lambda: self._browse_path(self.diff_a_var)).grid(row=0, column=0, padx=(240, 0), sticky="e")

        ctk.CTkLabel(f1, text="密码 A：").grid(row=1, column=0, sticky="w", pady=4)
        self.diff_apwd_var = ctk.StringVar()
        ctk.CTkEntry(f1, textvariable=self.diff_apwd_var, show="*", width=120).grid(row=1, column=0, padx=(80, 4), pady=4, sticky="w")

        f2 = ctk.CTkFrame(tab, fg_color="transparent")
        f2.grid(row=2, column=0, sticky="ew", padx=12, pady=2)
        f2.grid_columnconfigure((0, 2), weight=1)
        ctk.CTkLabel(f2, text="压缩包 B：").grid(row=0, column=0, sticky="w")
        self.diff_b_var = ctk.StringVar()
        ctk.CTkEntry(f2, textvariable=self.diff_b_var).grid(row=0, column=0, padx=(80, 4), sticky="ew")
        ctk.CTkButton(f2, text="浏览", width=70, command=lambda: self._browse_path(self.diff_b_var)).grid(row=0, column=0, padx=(240, 0), sticky="e")

        ctk.CTkLabel(f2, text="密码 B：").grid(row=1, column=0, sticky="w", pady=4)
        self.diff_bpwd_var = ctk.StringVar()
        ctk.CTkEntry(f2, textvariable=self.diff_bpwd_var, show="*", width=120).grid(row=1, column=0, padx=(80, 4), pady=4, sticky="w")

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=3, column=0, pady=8)
        self.diff_btn = ctk.CTkButton(btn_frame, text="🆚 开始对比", width=200, command=self._do_diff)
        self.diff_btn.pack()

        self.diff_log = ctk.CTkTextbox(tab, height=280, state="disabled", font=ctk.CTkFont(size=12))
        self.diff_log.grid(row=4, column=0, sticky="nsew", padx=12, pady=6)
        tab.grid_rowconfigure(4, weight=1)

    def _do_diff(self):
        a, b = self.diff_a_var.get(), self.diff_b_var.get()
        if not a or not b: return
        pa, pb = self.diff_apwd_var.get() or None, self.diff_bpwd_var.get() or None

        def task():
            return diff_archives(Path(a), Path(b), pa, pb)

        def cb(r: DiffResult):
            self.diff_log.configure(state="normal")
            self.diff_log.delete("1.0", "end")
            lines = [
                f"🆚 对比结果",
                f"{'='*50}",
                f"📄 仅在 A 中 ({len(r.only_in_a)}):",
            ]
            for f in r.only_in_a[:30]:
                lines.append(f"  - {f}")
            if len(r.only_in_a) > 30:
                lines.append(f"  ... 还有 {len(r.only_in_a)-30} 个")
            lines.append(f"")
            lines.append(f"📄 仅在 B 中 ({len(r.only_in_b)}):")
            for f in r.only_in_b[:30]:
                lines.append(f"  + {f}")
            if len(r.only_in_b) > 30:
                lines.append(f"  ... 还有 {len(r.only_in_b)-30} 个")
            lines.append(f"")
            lines.append(f"📄 内容不同 ({len(r.different)}):")
            for name, sa, sb in r.different[:20]:
                lines.append(f"  ~ {name}  ({fmt_size(sa)} vs {fmt_size(sb)})")
            if len(r.different) > 20:
                lines.append(f"  ... 还有 {len(r.different)-20} 个")
            lines.append(f"")
            lines.append(f"✅ 相同: {r.same}  总计差异: {r.total_diffs}")
            self.diff_log.insert("end", "\n".join(lines))
            self.diff_log.configure(state="disabled")

        run_in_thread(task, cb)


    # ══════════════════════════════════════════════════
    # 🔧 修复 —— Archive Repair
    # ══════════════════════════════════════════════════

    def _init_repair_tab(self):
        tab = self.tab_repair
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="从损坏的压缩包中恢复可读取的文件", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        row1 = ctk.CTkFrame(tab, fg_color="transparent")
        row1.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        row1.grid_columnconfigure(0, weight=1)
        self.rpr_src_var = ctk.StringVar()
        ctk.CTkEntry(row1, textvariable=self.rpr_src_var, placeholder_text="损坏的压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row1, text="浏览", width=80, command=lambda: self._browse_path(self.rpr_src_var)).grid(row=0, column=1)

        row2 = ctk.CTkFrame(tab, fg_color="transparent")
        row2.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        row2.grid_columnconfigure(0, weight=1)
        self.rpr_dst_var = ctk.StringVar()
        ctk.CTkEntry(row2, textvariable=self.rpr_dst_var, placeholder_text="输出路径（修复后的压缩包）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(row2, text="另存为", width=80, command=lambda: self._saveas_path(self.rpr_dst_var)).grid(row=0, column=1)

        opt = ctk.CTkFrame(tab, fg_color="transparent")
        opt.grid(row=3, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(opt, text="密码：").pack(side="left")
        self.rpr_pwd_var = ctk.StringVar()
        ctk.CTkEntry(opt, textvariable=self.rpr_pwd_var, show="*", width=120).pack(side="left", padx=(50, 0))

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=8)
        self.rpr_btn = ctk.CTkButton(btn_frame, text="🔧 开始修复", width=200, command=self._do_repair, fg_color="#d4760a")
        self.rpr_btn.pack()

        self.rpr_progress = ctk.CTkProgressBar(tab, mode="indeterminate")
        self.rpr_progress.grid(row=5, column=0, sticky="ew", padx=12, pady=4)

        self.rpr_log = ctk.CTkTextbox(tab, height=200, state="disabled")
        self.rpr_log.grid(row=6, column=0, sticky="nsew", padx=12, pady=6)
        tab.grid_rowconfigure(6, weight=1)

    def _do_repair(self):
        src = self.rpr_src_var.get()
        dst = self.rpr_dst_var.get()
        if not src or not dst: return
        pwd = self.rpr_pwd_var.get() or None

        self.rpr_btn.configure(state="disabled", text="修复中...")
        self.rpr_progress.start()
        self.log(self.rpr_log, f"🔧 开始修复: {src}")

        def task():
            return repair_archive(Path(src), Path(dst), password=pwd)

        def cb(result):
            success, failed, names = result
            self.rpr_progress.stop()
            self.rpr_btn.configure(state="normal", text="🔧 开始修复")
            self.log(self.rpr_log, f"✅ 修复完成: 成功 {success}, 失败 {failed}")
            if failed > 0 and names:
                self.log(self.rpr_log, f"❌ 无法恢复的文件 ({len(names)}):")
                for n in names[:20]:
                    self.log(self.rpr_log, f"   {n}")
                if len(names) > 20:
                    self.log(self.rpr_log, f"   ... 还有 {len(names)-20} 个")

        run_in_thread(task, cb)


    # ══════════════════════════════════════════════════
    # 🧹 清理 —— Smart Cleanup
    # ══════════════════════════════════════════════════

    def _init_cleanup_tab(self):
        tab = self.tab_cleanup
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="智能清理 —— 扫描旧文件/大文件并自动压缩归档", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        r1 = ctk.CTkFrame(tab, fg_color="transparent")
        r1.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        r1.grid_columnconfigure(0, weight=1)
        self.cln_dir_var = ctk.StringVar()
        ctk.CTkEntry(r1, textvariable=self.cln_dir_var, placeholder_text="要扫描的目录").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(r1, text="浏览", width=80, command=lambda: self._browse_dir(self.cln_dir_var)).grid(row=0, column=1)

        r2 = ctk.CTkFrame(tab, fg_color="transparent")
        r2.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(r2, text="多少天前的文件：").pack(side="left")
        self.cln_days_var = ctk.StringVar(value="30")
        ctk.CTkEntry(r2, textvariable=self.cln_days_var, width=60).pack(side="left", padx=6)
        ctk.CTkLabel(r2, text="最小大小 (MB)：").pack(side="left", padx=(20, 0))
        self.cln_size_var = ctk.StringVar(value="10")
        ctk.CTkEntry(r2, textvariable=self.cln_size_var, width=60).pack(side="left", padx=6)
        ctk.CTkLabel(r2, text="密码：").pack(side="left", padx=(20, 0))
        self.cln_pwd_var = ctk.StringVar()
        ctk.CTkEntry(r2, textvariable=self.cln_pwd_var, show="*", width=100).pack(side="left", padx=6)

        btn_f = ctk.CTkFrame(tab, fg_color="transparent")
        btn_f.grid(row=3, column=0, pady=6)
        self.cln_scan_btn = ctk.CTkButton(btn_f, text="🔍 仅扫描", width=120, command=lambda: self._do_cleanup(True))
        self.cln_scan_btn.pack(side="left", padx=4)
        self.cln_btn = ctk.CTkButton(btn_f, text="🧹 扫描+清理", width=160, command=lambda: self._do_cleanup(False), fg_color="#d4760a")
        self.cln_btn.pack(side="left", padx=4)

        self.cln_progress = ctk.CTkProgressBar(tab, mode="indeterminate")
        self.cln_progress.grid(row=4, column=0, sticky="ew", padx=12, pady=4)

        self.cln_log = ctk.CTkTextbox(tab, height=220, state="disabled")
        self.cln_log.grid(row=5, column=0, sticky="nsew", padx=12, pady=6)
        tab.grid_rowconfigure(5, weight=1)

    def _do_cleanup(self, dry_run=True):
        d = self.cln_dir_var.get()
        if not d: return
        days = int(self.cln_days_var.get() or 30)
        mb = int(self.cln_size_var.get() or 10)
        pwd = self.cln_pwd_var.get() or None

        self.cln_btn.configure(state="disabled")
        self.cln_scan_btn.configure(state="disabled")
        self.cln_progress.start()
        self.log(self.cln_log, f"🔍 扫描中: {d} ({days}天前, >{mb}MB)")

        def task():
            return smart_cleanup(Path(d), days, mb, dry_run=dry_run, password=pwd)

        def cb(r):
            self.cln_progress.stop()
            self.cln_btn.configure(state="normal")
            self.cln_scan_btn.configure(state="normal")
            mode = "🔍 扫描结果 (仅预览)" if r["dry_run"] else "🧹 清理结果"
            self.log(self.cln_log, f"{mode}")
            self.log(self.cln_log, f"  找到 {r['found']} 个符合条件文件")
            self.log(self.cln_log, f"  总大小: {r['total_size_fmt']}")
            if r["by_month"]:
                self.log(self.cln_log, f"  按月份: {dict(r['by_month'])}")
            if r["archives_created"]:
                for a in r["archives_created"]:
                    self.log(self.cln_log, f"  ✅ 已归档: {a}")
            if r["dry_run"]:
                self.log(self.cln_log, "  ℹ️ 这是预览模式，点击「扫描+清理」才会真正执行")

        def ec(e):
            self.cln_progress.stop()
            self.cln_btn.configure(state="normal")
            self.cln_scan_btn.configure(state="normal")
            self.log(self.cln_log, f"❌ {e}")

        run_in_thread(task, cb, ec)


    # ══════════════════════════════════════════════════
    # 📊 分析 —— Dedup + Checksum + 文件预览
    # ══════════════════════════════════════════════════

    def _init_analysis_tab(self):
        tab = self.tab_analysis
        tab.grid_columnconfigure(0, weight=1)

        # ── 子标签 ──
        self.ana_tabs = ctk.CTkTabview(tab)
        self.ana_tabs.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        # 去重
        dup_tab = self.ana_tabs.add("🔁 去重")
        dup_tab.grid_columnconfigure(0, weight=1)
        dup_r1 = ctk.CTkFrame(dup_tab, fg_color="transparent")
        dup_r1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        dup_r1.grid_columnconfigure(0, weight=1)
        self.dup_path_var = ctk.StringVar()
        ctk.CTkEntry(dup_r1, textvariable=self.dup_path_var, placeholder_text="扫描路径（目录或压缩包）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(dup_r1, text="浏览", width=80, command=lambda: self._browse_path(self.dup_path_var)).grid(row=0, column=1)
        btn_f = ctk.CTkFrame(dup_tab, fg_color="transparent")
        btn_f.grid(row=1, column=0, pady=4)
        self.dup_btn = ctk.CTkButton(btn_f, text="🔁 扫描重复文件", width=200, command=self._do_dedup)
        self.dup_btn.pack()
        self.dup_log = ctk.CTkTextbox(dup_tab, height=280, state="disabled")
        self.dup_log.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        dup_tab.grid_rowconfigure(2, weight=1)

        # 校验和
        chk_tab = self.ana_tabs.add("🔐 校验和")
        chk_tab.grid_columnconfigure(0, weight=1)
        chk_r1 = ctk.CTkFrame(chk_tab, fg_color="transparent")
        chk_r1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        chk_r1.grid_columnconfigure(0, weight=1)
        self.chk_path_var = ctk.StringVar()
        ctk.CTkEntry(chk_r1, textvariable=self.chk_path_var, placeholder_text="文件路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(chk_r1, text="浏览", width=80, command=lambda: self._browse_path(self.chk_path_var)).grid(row=0, column=1)
        btn_f2 = ctk.CTkFrame(chk_tab, fg_color="transparent")
        btn_f2.grid(row=1, column=0, pady=4)
        self.chk_btn = ctk.CTkButton(btn_f2, text="🔐 计算校验和", width=200, command=self._do_checksum)
        self.chk_btn.pack()
        self.chk_log = ctk.CTkTextbox(chk_tab, height=280, state="disabled", font=ctk.CTkFont(size=12))
        self.chk_log.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        chk_tab.grid_rowconfigure(2, weight=1)

        # 文件预览
        prv_tab = self.ana_tabs.add("👁 预览")
        prv_tab.grid_columnconfigure(0, weight=1)
        prv_r1 = ctk.CTkFrame(prv_tab, fg_color="transparent")
        prv_r1.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        prv_r1.grid_columnconfigure(0, weight=1)
        self.prv_path_var = ctk.StringVar()
        ctk.CTkEntry(prv_r1, textvariable=self.prv_path_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(prv_r1, text="浏览", width=70, command=lambda: self._browse_path(self.prv_path_var)).grid(row=0, column=1, padx=2)
        self.prv_file_var = ctk.StringVar()
        ctk.CTkEntry(prv_r1, textvariable=self.prv_file_var, placeholder_text="包内文件名").grid(row=0, column=2, sticky="ew", padx=(0, 4))
        self.prv_pwd_var = ctk.StringVar()
        ctk.CTkEntry(prv_r1, textvariable=self.prv_pwd_var, placeholder_text="密码", show="*", width=100).grid(row=0, column=3, padx=2)
        ctk.CTkButton(prv_r1, text="👁 预览", width=80, command=self._do_preview).grid(row=0, column=4)
        self.prv_log = ctk.CTkTextbox(prv_tab, height=300, state="disabled", font=ctk.CTkFont(size=12))
        self.prv_log.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        prv_tab.grid_rowconfigure(1, weight=1)


    def _do_dedup(self):
        path = self.dup_path_var.get()
        if not path: return

        def task():
            return find_duplicates([Path(path)])

        def cb(groups):
            self.dup_log.configure(state="normal")
            self.dup_log.delete("1.0", "end")
            if not groups:
                self.dup_log.insert("end", "✅ 未发现重复文件")
                self.dup_log.configure(state="disabled")
                return
            total_waste = sum(g.wasted_bytes for g in groups)
            self.dup_log.insert("end",
                f"🔁 发现 {len(groups)} 组重复文件\n"
                f"浪费空间: {fmt_size(total_waste)}\n"
                f"{'='*50}\n\n"
            )
            for g in groups[:20]:
                self.dup_log.insert("end",
                    f"📦 [{g.hash[:8]}...] 大小: {fmt_size(g.size)}\n"
                )
                for f in g.files[:10]:
                    self.dup_log.insert("end", f"   📄 {f}\n")
                if len(g.files) > 10:
                    self.dup_log.insert("end", f"   ... 还有 {len(g.files)-10} 个\n")
                self.dup_log.insert("end", f"   💸 浪费 {fmt_size(g.wasted_bytes)}\n\n")
            if len(groups) > 20:
                self.dup_log.insert("end", f"... 还有 {len(groups)-20} 组\n")
            self.dup_log.configure(state="disabled")

        run_in_thread(task, cb)


    def _do_checksum(self):
        path = self.chk_path_var.get()
        if not path: return

        def task():
            return checksum_file(Path(path))

        def cb(hashes):
            self.chk_log.configure(state="normal")
            self.chk_log.delete("1.0", "end")
            self.chk_log.insert("end",
                f"🔐 校验和 — {Path(path).name}\n"
                f"{'='*60}\n\n"
            )
            for algo, h in hashes.items():
                self.chk_log.insert("end", f"{algo}: {h}\n")
            self.chk_log.configure(state="disabled")

        run_in_thread(task, cb)


    def _do_preview(self):
        path = self.prv_path_var.get()
        fname = self.prv_file_var.get()
        if not path or not fname: return
        pwd = self.prv_pwd_var.get() or None

        def task():
            return preview_file_in_archive(Path(path), fname, password=pwd)

        def cb(content):
            self.prv_log.configure(state="normal")
            self.prv_log.delete("1.0", "end")
            self.prv_log.insert("end", content)
            self.prv_log.configure(state="disabled")

        def ec(e):
            self.prv_log.configure(state="normal")
            self.prv_log.delete("1.0", "end")
            self.prv_log.insert("end", f"❌ 无法预览: {e}")
            self.prv_log.configure(state="disabled")

        run_in_thread(task, cb, ec)


    # ══════════════════════════════════════════════════
    # 🔮 智能 —— AI 密码 + 格式推荐 + 分类打包 + 模板
    # ══════════════════════════════════════════════════

    def _init_ai_tab(self):
        tab = self.tab_ai
        tab.grid_columnconfigure(0, weight=1)

        self.ai_tabs = ctk.CTkTabview(tab)
        self.ai_tabs.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        # ── 智能密码 ──
        pwd_tab = self.ai_tabs.add("🔑 智能密码")
        pwd_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(pwd_tab, text="根据文件名/上下文自动生成密码候选，用于破解", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        r = ctk.CTkFrame(pwd_tab, fg_color="transparent")
        r.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        r.grid_columnconfigure(0, weight=1)
        self.ai_pwd_var = ctk.StringVar()
        ctk.CTkEntry(r, textvariable=self.ai_pwd_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(r, text="浏览", width=80, command=lambda: self._browse_path(self.ai_pwd_var)).grid(row=0, column=1)
        ctk.CTkButton(pwd_tab, text="🔑 生成密码候选", command=self._do_ai_password).grid(row=2, column=0, pady=6)
        self.ai_pwd_log = ctk.CTkTextbox(pwd_tab, height=250, state="disabled")
        self.ai_pwd_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        pwd_tab.grid_rowconfigure(3, weight=1)

        # ── 格式推荐 ──
        fmt_tab = self.ai_tabs.add("🎯 格式推荐")
        fmt_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(fmt_tab, text="分析文件类型，智能推荐最佳压缩格式", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        r2 = ctk.CTkFrame(fmt_tab, fg_color="transparent")
        r2.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        r2.grid_columnconfigure(0, weight=1)
        self.ai_fmt_var = ctk.StringVar()
        ctk.CTkEntry(r2, textvariable=self.ai_fmt_var, placeholder_text="文件或文件夹路径（多个用;分隔）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(r2, text="浏览", width=80, command=lambda: self._browse_path(self.ai_fmt_var)).grid(row=0, column=1)
        ctk.CTkButton(fmt_tab, text="🎯 分析推荐", command=self._do_ai_format).grid(row=2, column=0, pady=6)
        self.ai_fmt_log = ctk.CTkTextbox(fmt_tab, height=200, state="disabled")
        self.ai_fmt_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        fmt_tab.grid_rowconfigure(3, weight=1)

        # ── 模板系统 ──
        tpl_tab = self.ai_tabs.add("📋 模板")
        tpl_tab.grid_columnconfigure(0, weight=1)

        # 模板选择
        r3 = ctk.CTkFrame(tpl_tab, fg_color="transparent")
        r3.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        r3.grid_columnconfigure(1, weight=1)
        self.tpl_names = sorted(get_templates().keys())
        self.tpl_var = ctk.StringVar(value=self.tpl_names[0])
        ctk.CTkLabel(r3, text="模板：").grid(row=0, column=0, padx=6)
        ctk.CTkOptionMenu(r3, variable=self.tpl_var, values=self.tpl_names).grid(row=0, column=1, padx=6, sticky="w")

        self.tpl_btn = ctk.CTkButton(tpl_tab, text="📋 使用模板压缩", command=self._do_template)
        self.tpl_btn.grid(row=1, column=0, pady=4)
        self.tpl_log = ctk.CTkTextbox(tpl_tab, height=300, state="disabled")
        self.tpl_log.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        tpl_tab.grid_rowconfigure(2, weight=1)

        # ── 分类打包 ──
        cls_tab = self.ai_tabs.add("📂 分类打包")
        cls_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cls_tab, text="按文件类型或日期自动分类打包", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        cr = ctk.CTkFrame(cls_tab, fg_color="transparent")
        cr.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        cr.grid_columnconfigure(0, weight=1)
        self.ai_cls_dir_var = ctk.StringVar()
        ctk.CTkEntry(cr, textvariable=self.ai_cls_dir_var, placeholder_text="源目录").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(cr, text="浏览", width=80, command=lambda: self._browse_dir(self.ai_cls_dir_var)).grid(row=0, column=1)
        cr2 = ctk.CTkFrame(cls_tab, fg_color="transparent")
        cr2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        cr2.grid_columnconfigure((0, 1, 2), weight=1)
        self.ai_cls_by_var = ctk.StringVar(value="type")
        ctk.CTkOptionMenu(cr2, variable=self.ai_cls_by_var, values=["type (按类型)", "date (按日期)"]).grid(row=0, column=0, padx=2)
        self.ai_cls_out_var = ctk.StringVar()
        ctk.CTkEntry(cr2, textvariable=self.ai_cls_out_var, placeholder_text="输出目录").grid(row=0, column=1, sticky="ew", padx=2)
        ctk.CTkButton(cr2, text="浏览", width=70, command=lambda: self._browse_dir(self.ai_cls_out_var)).grid(row=0, column=2, padx=2)
        ctk.CTkButton(cls_tab, text="📂 开始分类打包", command=self._do_classify).grid(row=3, column=0, pady=6)
        self.ai_cls_log = ctk.CTkTextbox(cls_tab, height=220, state="disabled")
        self.ai_cls_log.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        cls_tab.grid_rowconfigure(4, weight=1)

    def _do_ai_password(self):
        p = self.ai_pwd_var.get()
        if not p: return

        def task():
            cand = smart_password_candidates(Path(p))
            return cand

        def cb(cand):
            self.ai_pwd_log.configure(state="normal")
            self.ai_pwd_log.delete("1.0", "end")
            self.ai_pwd_log.insert("end",
                f"🔑 生成 {len(cand)} 个密码候选:\n"
                f"{'='*50}\n\n"
            )
            # 分组显示
            self.ai_pwd_log.insert("end", "🎯 Top 20:\n")
            for i, c in enumerate(cand[:20], 1):
                self.ai_pwd_log.insert("end", f"  {i:2d}. {c}\n")
            if len(cand) > 20:
                self.ai_pwd_log.insert("end", f"\n... 还有 {len(cand)-20} 个\n")
            self.ai_pwd_log.configure(state="disabled")

        run_in_thread(task, cb)

    def _do_ai_format(self):
        p = self.ai_fmt_var.get()
        if not p: return
        paths = [Path(x.strip()) for x in p.split(";") if x.strip()]

        def task():
            return recommend_format(paths)

        def cb(r):
            self.ai_fmt_log.configure(state="normal")
            self.ai_fmt_log.delete("1.0", "end")
            self.ai_fmt_log.insert("end",
                f"🎯 推荐格式: [bold]{r['format']}[/]\n"
                f"📋 理由: {r['reason']}\n"
                f"🔧 建议参数: {r['filters']}\n"
            )
            self.ai_fmt_log.configure(state="disabled")

        run_in_thread(task, cb)

    def _do_template(self):
        name = self.tpl_var.get()
        tpl = get_templates()[name]
        self.tpl_log.configure(state="normal")
        self.tpl_log.delete("1.0", "end")
        info = tpl
        status = "需要密码" if info["password"] is True else ("无密码" if not info["password"] else info["password"])
        vol = f"分卷 {info['volume']/1024**2:.0f}MB" if info["volume"] else "不分卷"
        self.tpl_log.insert("end",
            f"📋 模板: {info['name']}\n"
            f"{'='*40}\n"
            f"格式: {info['format']}\n"
            f"密码: {status}\n"
            f"分卷: {vol}\n"
            f"说明: {info['description']}\n\n"
            f"💡 请到「📦 压缩」标签页手动应用此配置\n"
        )
        self.tpl_log.configure(state="disabled")

    def _do_classify(self):
        src = self.ai_cls_dir_var.get()
        out = self.ai_cls_out_var.get()
        by = self.ai_cls_by_var.get().split()[0]
        if not src or not out: return

        def task():
            return auto_classify(Path(src), Path(out), by=by)

        def cb(files):
            self.ai_cls_log.configure(state="normal")
            self.ai_cls_log.delete("1.0", "end")
            self.ai_cls_log.insert("end", f"✅ 分类打包完成: {len(files)} 个压缩包\n\n")
            for f in files:
                self.ai_cls_log.insert("end", f"  📦 {f.name} ({_fmt_size(f.stat().st_size)})\n")
            self.ai_cls_log.configure(state="disabled")

        run_in_thread(task, cb)


    # ══════════════════════════════════════════════════
    # 🔍 扫描 —— 健康报告 + 空间浪费 + 全文搜索
    # ══════════════════════════════════════════════════

    def _init_scan_tab(self):
        tab = self.tab_scan
        tab.grid_columnconfigure(0, weight=1)

        self.scan_tabs = ctk.CTkTabview(tab)
        self.scan_tabs.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        # ── 健康报告 ──
        hlth = self.scan_tabs.add("📋 健康报告")
        hlth.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hlth, text="扫描目录下所有压缩包，生成完整健康报告").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        hr = ctk.CTkFrame(hlth, fg_color="transparent")
        hr.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        hr.grid_columnconfigure(0, weight=1)
        self.scan_hlth_var = ctk.StringVar()
        ctk.CTkEntry(hr, textvariable=self.scan_hlth_var, placeholder_text="要扫描的目录").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(hr, text="浏览", width=80, command=lambda: self._browse_dir(self.scan_hlth_var)).grid(row=0, column=1)
        ctk.CTkButton(hlth, text="📋 生成报告", command=self._do_health_report).grid(row=2, column=0, pady=6)
        self.scan_hlth_log = ctk.CTkTextbox(hlth, height=250, state="disabled")
        self.scan_hlth_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        hlth.grid_rowconfigure(3, weight=1)

        # ── 空间浪费 ──
        wst = self.scan_tabs.add("💸 空间浪费")
        wst.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(wst, text="找出全盘压缩率最差的压缩包（重新压缩可省空间）").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        wr = ctk.CTkFrame(wst, fg_color="transparent")
        wr.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        wr.grid_columnconfigure(0, weight=1)
        self.scan_wst_var = ctk.StringVar()
        ctk.CTkEntry(wr, textvariable=self.scan_wst_var, placeholder_text="要扫描的目录").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(wr, text="浏览", width=80, command=lambda: self._browse_dir(self.scan_wst_var)).grid(row=0, column=1)
        ctk.CTkButton(wst, text="💸 分析浪费", command=self._do_space_waste).grid(row=2, column=0, pady=6)
        self.scan_wst_log = ctk.CTkTextbox(wst, height=250, state="disabled")
        self.scan_wst_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        wst.grid_rowconfigure(3, weight=1)

        # ── 全文搜索 ──
        sch = self.scan_tabs.add("🔎 全文搜索")
        sch.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(sch, text="跨压缩包搜索文件内容（支持通配符）").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        sr = ctk.CTkFrame(sch, fg_color="transparent")
        sr.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        sr.grid_columnconfigure(0, weight=1)
        self.scan_sch_pat_var = ctk.StringVar()
        ctk.CTkEntry(sr, textvariable=self.scan_sch_pat_var, placeholder_text="通配符，如 D:/archives/*.7z").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        sr2 = ctk.CTkFrame(sch, fg_color="transparent")
        sr2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        sr2.grid_columnconfigure((0, 1), weight=1)
        self.scan_sch_kw_var = ctk.StringVar()
        ctk.CTkEntry(sr2, textvariable=self.scan_sch_kw_var, placeholder_text="搜索关键词").grid(row=0, column=0, sticky="ew", padx=2)
        ctk.CTkButton(sr2, text="🔍 搜索", command=self._do_fulltext_search).grid(row=0, column=1, padx=2)
        self.scan_sch_log = ctk.CTkTextbox(sch, height=280, state="disabled")
        self.scan_sch_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        sch.grid_rowconfigure(3, weight=1)

    def _do_health_report(self):
        d = self.scan_hlth_var.get()
        if not d: return

        def task():
            return health_report(Path(d))

        def cb(r):
            self.scan_hlth_log.configure(state="normal")
            self.scan_hlth_log.delete("1.0", "end")
            self.scan_hlth_log.insert("end",
                f"📋 压缩包健康报告\n"
                f"{'='*50}\n"
                f"总计: {r['total_archives']} 个压缩包\n"
                f"总大小: {r['total_size_fmt']}\n"
                f"加密: {r['encrypted']} 个 | 弱加密: {r['encrypted_weak']} 个 | 未加密: {r['unencrypted']} 个\n"
                f"损坏: {len(r['corrupted'])} 个\n"
                f"\n格式分布: {dict(r['by_format'])}\n"
            )
            if r['issues']:
                self.scan_hlth_log.insert("end", f"\n⚠ 发现的问题:\n")
                for iss in r['issues'][:20]:
                    self.scan_hlth_log.insert("end", f"  {iss}\n")
            if r['largest']:
                self.scan_hlth_log.insert("end", f"\n最大文件 Top 5:\n")
                for name, sz in r['largest'][:5]:
                    self.scan_hlth_log.insert("end", f"  📦 {name} ({_fmt_size(sz)})\n")
            self.scan_hlth_log.configure(state="disabled")

        run_in_thread(task, cb)

    def _do_space_waste(self):
        d = self.scan_wst_var.get()
        if not d: return

        def task():
            return space_waste_analysis(Path(d))

        def cb(items):
            self.scan_wst_log.configure(state="normal")
            self.scan_wst_log.delete("1.0", "end")
            if not items:
                self.scan_wst_log.insert("end", "✅ 未发现明显浪费空间的压缩包\n")
            else:
                total = sum(x['wasted_bytes'] for x in items)
                self.scan_wst_log.insert("end",
                    f"💸 发现 {len(items)} 个压缩率差的压缩包\n"
                    f"可节省空间: {_fmt_size(total)}\n"
                    f"{'='*50}\n\n"
                )
                for item in items[:15]:
                    self.scan_wst_log.insert("end",
                        f"📦 {item['name']}\n"
                        f"   格式: {item['format']} | 压缩率: {item['ratio']*100:.1f}%\n"
                        f"   原始: {_fmt_size(item['raw_size'])} → 压缩: {_fmt_size(item['compressed_size'])}\n"
                        f"   可省: {item['wasted_fmt']}\n\n"
                    )
            self.scan_wst_log.configure(state="disabled")

        run_in_thread(task, cb)

    def _do_fulltext_search(self):
        pat = self.scan_sch_pat_var.get()
        kw = self.scan_sch_kw_var.get()
        if not pat or not kw: return

        def task():
            return fulltext_search_archives([pat], kw)

        def cb(results):
            self.scan_sch_log.configure(state="normal")
            self.scan_sch_log.delete("1.0", "end")
            if not results:
                self.scan_sch_log.insert("end", f"🔍 搜索「{kw}」未找到结果\n")
            else:
                self.scan_sch_log.insert("end",
                    f"🔍 搜索「{kw}」找到 {len(results)} 个匹配\n"
                    f"{'='*50}\n\n"
                )
                for r in results[:30]:
                    self.scan_sch_log.insert("end",
                        f"📦 [{r['archive']}] {r['file']} ({r['matches']} 处匹配)\n"
                    )
                    if r['context']:
                        self.scan_sch_log.insert("end", f"{r['context']}\n")
            self.scan_sch_log.configure(state="disabled")

        run_in_thread(task, cb)


    # ══════════════════════════════════════════════════
    # ✏️ 编辑 —— 替换/删除/递归解压/隐写检测
    # ══════════════════════════════════════════════════

    def _init_edit_tab(self):
        tab = self.tab_edit
        tab.grid_columnconfigure(0, weight=1)

        self.edit_tabs = ctk.CTkTabview(tab)
        self.edit_tabs.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        # ── 替换/删除 ──
        mod = self.edit_tabs.add("✏️ 修改")
        mod.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(mod, text="替换或删除压缩包内的文件（提取→修改→重新打包）").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        mr = ctk.CTkFrame(mod, fg_color="transparent")
        mr.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        mr.grid_columnconfigure(0, weight=1)
        self.ed_arc_var = ctk.StringVar()
        ctk.CTkEntry(mr, textvariable=self.ed_arc_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(mr, text="浏览", width=80, command=lambda: self._browse_path(self.ed_arc_var)).grid(row=0, column=1)
        mr2 = ctk.CTkFrame(mod, fg_color="transparent")
        mr2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        mr2.grid_columnconfigure((0, 1), weight=1)
        self.ed_file_var = ctk.StringVar()
        ctk.CTkEntry(mr2, textvariable=self.ed_file_var, placeholder_text="包内文件名（如 dir/file.txt）").grid(row=0, column=0, sticky="ew", padx=2)
        self.ed_pwd_var = ctk.StringVar()
        ctk.CTkEntry(mr2, textvariable=self.ed_pwd_var, placeholder_text="密码", show="*", width=120).grid(row=0, column=1, padx=2)
        mr3 = ctk.CTkFrame(mod, fg_color="transparent")
        mr3.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkButton(mr3, text="🗑 删除此文件", command=self._do_edit_delete, fg_color="#da3633").grid(row=0, column=0, padx=4)
        self.ed_log = ctk.CTkTextbox(mod, height=250, state="disabled")
        self.ed_log.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        mod.grid_rowconfigure(4, weight=1)

        # ── 递归解压 ──
        rec = self.edit_tabs.add("🔁 递归解压")
        rec.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(rec, text="自动解压嵌套压缩包（压缩包里的压缩包）").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        rr = ctk.CTkFrame(rec, fg_color="transparent")
        rr.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        rr.grid_columnconfigure(0, weight=1)
        self.ed_rec_var = ctk.StringVar()
        ctk.CTkEntry(rr, textvariable=self.ed_rec_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(rr, text="浏览", width=80, command=lambda: self._browse_path(self.ed_rec_var)).grid(row=0, column=1)
        rr2 = ctk.CTkFrame(rec, fg_color="transparent")
        rr2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        rr2.grid_columnconfigure((0, 1), weight=1)
        self.ed_rec_out_var = ctk.StringVar()
        ctk.CTkEntry(rr2, textvariable=self.ed_rec_out_var, placeholder_text="输出目录").grid(row=0, column=0, sticky="ew", padx=2)
        ctk.CTkButton(rr2, text="浏览", width=70, command=lambda: self._browse_dir(self.ed_rec_out_var)).grid(row=0, column=1, padx=2)
        ctk.CTkButton(rec, text="🔁 开始递归解压", command=self._do_recursive).grid(row=3, column=0, pady=6)
        self.ed_rec_log = ctk.CTkTextbox(rec, height=250, state="disabled")
        self.ed_rec_log.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        rec.grid_rowconfigure(4, weight=1)

        # ── 隐写检测 ──
        steg = self.edit_tabs.add("🔍 隐写检测")
        steg.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(steg, text="检查压缩包是否有隐藏数据、尾部附加内容").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        sr = ctk.CTkFrame(steg, fg_color="transparent")
        sr.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        sr.grid_columnconfigure(0, weight=1)
        self.ed_steg_var = ctk.StringVar()
        ctk.CTkEntry(sr, textvariable=self.ed_steg_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(sr, text="浏览", width=80, command=lambda: self._browse_path(self.ed_steg_var)).grid(row=0, column=1)
        ctk.CTkButton(steg, text="🔍 检测隐藏数据", command=self._do_steganography).grid(row=2, column=0, pady=6)
        self.ed_steg_log = ctk.CTkTextbox(steg, height=250, state="disabled")
        self.ed_steg_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        steg.grid_rowconfigure(3, weight=1)

    def _do_edit_delete(self):
        arc = self.ed_arc_var.get()
        fname = self.ed_file_var.get()
        pwd = self.ed_pwd_var.get() or None
        if not arc or not fname: return

        def task():
            return delete_from_archive(Path(arc), fname, password=pwd)

        def cb(out):
            self.ed_log.configure(state="normal")
            self.ed_log.delete("1.0", "end")
            self.ed_log.insert("end", f"✅ 已从压缩包中删除: {fname}\n")
            self.ed_log.insert("end", f"📦 输出: {out}\n")
            self.ed_log.configure(state="disabled")

        def ec(e):
            self.ed_log.configure(state="normal")
            self.ed_log.delete("1.0", "end")
            self.ed_log.insert("end", f"❌ 删除失败: {e}\n")
            self.ed_log.configure(state="disabled")

        run_in_thread(task, cb, ec)

    def _do_recursive(self):
        arc = self.ed_rec_var.get()
        out = self.ed_rec_out_var.get()
        if not arc or not out: return

        def task():
            return recursive_extract(Path(arc), Path(out))

        def cb(stats):
            self.ed_rec_log.configure(state="normal")
            self.ed_rec_log.delete("1.0", "end")
            self.ed_rec_log.insert("end",
                f"✅ 递归解压完成\n"
                f"  解压层数: {stats['depth_reached']}\n"
                f"  发现嵌套包: {stats['nested_found']} 个\n"
                f"  失败: {len(stats['failed'])} 个\n"
            )
            if stats['failed']:
                for f in stats['failed'][:10]:
                    self.ed_rec_log.insert("end", f"  ❌ {f}\n")
            self.ed_rec_log.configure(state="disabled")

        run_in_thread(task, cb)

    def _do_steganography(self):
        arc = self.ed_steg_var.get()
        if not arc: return

        def task():
            return steganography_check(Path(arc))

        def cb(r):
            self.ed_steg_log.configure(state="normal")
            self.ed_steg_log.delete("1.0", "end")
            status = "✅ 安全" if r['safe'] else "⚠ 发现异常"
            self.ed_steg_log.insert("end", f"🔍 隐写检测: {status}\n{'='*50}\n")
            if r['issues']:
                for iss in r['issues']:
                    self.ed_steg_log.insert("end", f"  ⚠ {iss}\n")
            else:
                self.ed_steg_log.insert("end", "  未发现隐藏数据\n")
            self.ed_steg_log.configure(state="disabled")

        run_in_thread(task, cb)


    # ══════════════════════════════════════════════════
    # 🧬 混合 —— 多算法混合压缩 + 图片优化打包
    # ══════════════════════════════════════════════════

    def _init_hybrid_tab(self):
        tab = self.tab_hybrid
        tab.grid_columnconfigure(0, weight=1)

        self.hyb_tabs = ctk.CTkTabview(tab)
        self.hyb_tabs.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        # ── 混合压缩 ──
        hc = self.hyb_tabs.add("🧬 混合压缩")
        hc.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hc, text="多算法混合压缩引擎——每个文件类型用最优算法", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        hr1 = ctk.CTkFrame(hc, fg_color="transparent")
        hr1.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        hr1.grid_columnconfigure(0, weight=1)
        self.hyb_src_var = ctk.StringVar()
        ctk.CTkEntry(hr1, textvariable=self.hyb_src_var, placeholder_text="文件/文件夹路径（;分隔多个）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(hr1, text="浏览", width=80, command=lambda: self._browse_path(self.hyb_src_var)).grid(row=0, column=1)

        hr2 = ctk.CTkFrame(hc, fg_color="transparent")
        hr2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        hr2.grid_columnconfigure(0, weight=1)
        self.hyb_out_var = ctk.StringVar()
        ctk.CTkEntry(hr2, textvariable=self.hyb_out_var, placeholder_text="输出路径（如 D:/hybrid.7z）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(hr2, text="另存为", width=80, command=lambda: self._saveas_path(self.hyb_out_var)).grid(row=0, column=1)

        hr3 = ctk.CTkFrame(hc, fg_color="transparent")
        hr3.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        hr3.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hr3, text="算法策略展示:", anchor="w").grid(row=0, column=0, sticky="w")
        strat = ctk.CTkTextbox(hr3, height=80, state="normal")
        strat.grid(row=1, column=0, sticky="ew", pady=4)
        strat.insert("end",
            "📄 文本 → PPMd (压缩率最高)\n"
            "🖼 图片 → Store (已压缩, 不浪费时间)\n"
            "⚙️ EXE → LZMA2 Level 9 (极限压缩)\n"
            "📁 其他 → LZMA2 Level 5 (均衡)"
        )
        strat.configure(state="disabled")

        self.hyb_btn = ctk.CTkButton(hc, text="🧬 混合压缩", height=36, command=self._do_hybrid, fg_color="#a371f7")
        self.hyb_btn.grid(row=4, column=0, pady=6)

        self.hyb_log = ctk.CTkTextbox(hc, height=180, state="disabled")
        self.hyb_log.grid(row=5, column=0, sticky="nsew", padx=8, pady=4)
        hc.grid_rowconfigure(5, weight=1)

        # ── 图片优化打包 ──
        ip = self.hyb_tabs.add("🖼 图片优化")
        ip.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(ip, text="专为摄影师设计——自动优化图片后打包", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        ir1 = ctk.CTkFrame(ip, fg_color="transparent")
        ir1.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ir1.grid_columnconfigure(0, weight=1)
        self.img_src_var = ctk.StringVar()
        ctk.CTkEntry(ir1, textvariable=self.img_src_var, placeholder_text="图片目录").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(ir1, text="浏览", width=80, command=lambda: self._browse_dir(self.img_src_var)).grid(row=0, column=1)

        ir2 = ctk.CTkFrame(ip, fg_color="transparent")
        ir2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        ir2.grid_columnconfigure(0, weight=1)
        self.img_out_var = ctk.StringVar()
        ctk.CTkEntry(ir2, textvariable=self.img_out_var, placeholder_text="输出压缩包").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(ir2, text="另存为", width=80, command=lambda: self._saveas_path(self.img_out_var)).grid(row=0, column=1)

        ir3 = ctk.CTkFrame(ip, fg_color="transparent")
        ir3.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(ir3, text="JPEG 质量:").pack(side="left")
        self.img_qual_var = ctk.StringVar(value="85")
        ctk.CTkEntry(ir3, textvariable=self.img_qual_var, width=60).pack(side="left", padx=6)
        ctk.CTkLabel(ir3, text="最大宽度:").pack(side="left", padx=(20,0))
        self.img_width_var = ctk.StringVar()
        ctk.CTkEntry(ir3, textvariable=self.img_width_var, placeholder_text="留空不限", width=80).pack(side="left", padx=6)
        ctk.CTkLabel(ir3, text="密码:").pack(side="left", padx=(20,0))
        self.img_pwd_var = ctk.StringVar()
        ctk.CTkEntry(ir3, textvariable=self.img_pwd_var, show="*", width=100).pack(side="left", padx=6)

        self.img_btn = ctk.CTkButton(ip, text="🖼 优化并打包", height=36, command=self._do_image_pack, fg_color="#3fb950")
        self.img_btn.grid(row=4, column=0, pady=6)

        self.img_log = ctk.CTkTextbox(ip, height=200, state="disabled")
        self.img_log.grid(row=5, column=0, sticky="nsew", padx=8, pady=4)
        ip.grid_rowconfigure(5, weight=1)

    def _do_hybrid(self):
        src = self.hyb_src_var.get()
        out = self.hyb_out_var.get()
        if not src or not out: return
        sources = [Path(s.strip()) for s in src.split(";") if s.strip()]

        self.hyb_btn.configure(state="disabled", text="压缩中...")

        def task():
            return hybrid_compress(sources, Path(out))

        def cb(p):
            self.hyb_btn.configure(state="normal", text="🧬 混合压缩")
            self.hyb_log.configure(state="normal")
            self.hyb_log.delete("1.0", "end")
            self.hyb_log.insert("end", f"✅ 混合压缩完成\n")
            self.hyb_log.insert("end", f"📦 {p.name} ({_fmt_size(p.stat().st_size)})\n")
            self.hyb_log.configure(state="disabled")

        def ec(e):
            self.hyb_btn.configure(state="normal", text="🧬 混合压缩")
            self.hyb_log.configure(state="normal")
            self.hyb_log.insert("end", f"❌ {e}\n")
            self.hyb_log.configure(state="disabled")

        run_in_thread(task, cb, ec)

    def _do_image_pack(self):
        src = self.img_src_var.get()
        out = self.img_out_var.get()
        quality = int(self.img_qual_var.get() or 85)
        max_w = int(self.img_width_var.get()) if self.img_width_var.get() else None
        pwd = self.img_pwd_var.get() or None
        if not src or not out: return

        self.img_btn.configure(state="disabled", text="优化中...")

        def task():
            return image_optimized_pack([Path(src)], Path(out),
                                        jpeg_quality=quality, max_width=max_w,
                                        password=pwd)

        def cb(p):
            self.img_btn.configure(state="normal", text="🖼 优化并打包")
            self.img_log.configure(state="normal")
            self.img_log.delete("1.0", "end")
            self.img_log.insert("end", f"✅ 图片优化打包完成\n")
            self.img_log.insert("end", f"📦 {p.name} ({_fmt_size(p.stat().st_size)})\n")
            self.img_log.configure(state="disabled")

        def ec(e):
            self.img_btn.configure(state="normal", text="🖼 优化并打包")
            self.img_log.configure(state="normal")
            self.img_log.insert("end", f"❌ {e}\n")
            self.img_log.configure(state="disabled")

        run_in_thread(task, cb, ec)


    # ══════════════════════════════════════════════════
    # 🔧 管道 —— Pipeline 链式操作
    # ══════════════════════════════════════════════════

    def _init_pipeline_tab(self):
        tab = self.tab_pipeline
        tab.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(tab, text="压缩管道——链式自动化操作引擎", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(tab, text="一行命令完成：下载→解压→清理→去重→优化图片→压缩→分卷→校验", font=ctk.CTkFont(size=11)).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))

        # 管道脚本输入
        ctk.CTkLabel(tab, text="管道脚本（每行一步）:").grid(row=2, column=0, sticky="w", padx=12, pady=(4, 2))
        self.pipe_script = ctk.CTkTextbox(tab, height=120, font=ctk.CTkFont(size=12))
        self.pipe_script.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))
        self.pipe_script.insert("end",
            "# 示例: 下载→解压→清理→去重→压缩→分卷\n"
            "download url=https://example.com/file.zip\n"
            "extract\n"
            "clean\n"
            "dedup\n"
            "optimize_images jpeg_quality=80\n"
            "compress output=result.7z hybrid=true\n"
            "split volume=10M\n"
        )

        # 预设管道
        presets_frame = ctk.CTkFrame(tab, fg_color="transparent")
        presets_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkLabel(presets_frame, text="预设管道:").pack(side="left")
        ctk.CTkButton(presets_frame, text="📷 图片优化", command=lambda: self._pipe_preset("photo"), width=100).pack(side="left", padx=4)
        ctk.CTkButton(presets_frame, text="📦 打包备份", command=lambda: self._pipe_preset("backup"), width=100).pack(side="left", padx=4)
        ctk.CTkButton(presets_frame, text="🌐 下载打包", command=lambda: self._pipe_preset("download"), width=100).pack(side="left", padx=4)

        # 操作按钮
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.grid(row=5, column=0, pady=6)
        self.pipe_btn = ctk.CTkButton(btn_frame, text="🔧 执行管道", height=36, command=self._do_pipeline, fg_color="#d4760a")
        self.pipe_btn.pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="📋 预览步骤", command=self._pipe_preview).pack(side="left", padx=4)

        self.pipe_progress = ctk.CTkProgressBar(tab, mode="indeterminate")
        self.pipe_progress.grid(row=6, column=0, sticky="ew", padx=12, pady=4)

        self.pipe_log = ctk.CTkTextbox(tab, height=240, state="disabled")
        self.pipe_log.grid(row=7, column=0, sticky="nsew", padx=12, pady=4)
        tab.grid_rowconfigure(7, weight=1)

    def _pipe_preset(self, name):
        presets = {
            "photo": (
                "optimize_images jpeg_quality=85\n"
                "strip_exif\n"
                "dedup\n"
                "compress output=photos.7z hybrid=true\n"
                "checksum\n"
            ),
            "backup": (
                "clean\n"
                "dedup\n"
                "compress output=backup.7z hybrid=true\n"
                "split volume=50M\n"
                "checksum\n"
            ),
            "download": (
                "download url=\n"
                "extract\n"
                "clean\n"
                "optimize_images jpeg_quality=80\n"
                "compress output=result.7z hybrid=true\n"
                "checksum\n"
            ),
        }
        self.pipe_script.delete("1.0", "end")
        self.pipe_script.insert("end", presets.get(name, ""))

    def _pipe_preview(self):
        text = self.pipe_script.get("1.0", "end").strip()
        try:
            pipe = pipeline_from_yaml(text)
            self.pipe_log.configure(state="normal")
            self.pipe_log.delete("1.0", "end")
            self.pipe_log.insert("end", pipe.describe())
            self.pipe_log.configure(state="disabled")
        except Exception as e:
            self.pipe_log.configure(state="normal")
            self.pipe_log.delete("1.0", "end")
            self.pipe_log.insert("end", f"❌ 解析失败: {e}")
            self.pipe_log.configure(state="disabled")

    def _do_pipeline(self):
        text = self.pipe_script.get("1.0", "end").strip()
        if not text: return

        self.pipe_btn.configure(state="disabled", text="执行中...")
        self.pipe_progress.start()
        self.pipe_log.configure(state="normal")
        self.pipe_log.delete("1.0", "end")
        self.pipe_log.insert("end", "🔧 启动管道...\n")
        self.pipe_log.configure(state="disabled")

        def task():
            pipe = pipeline_from_yaml(text)
            return pipe.run()

        def cb(results):
            self.pipe_progress.stop()
            self.pipe_btn.configure(state="normal", text="🔧 执行管道")
            self.pipe_log.configure(state="normal")
            for r in results:
                self.pipe_log.insert("end", f"  ✅ {r}\n")
            self.pipe_log.insert("end", "\n✅ 管道执行完成")
            self.pipe_log.configure(state="disabled")

        def ec(e):
            self.pipe_progress.stop()
            self.pipe_btn.configure(state="normal", text="🔧 执行管道")
            self.pipe_log.configure(state="normal")
            self.pipe_log.insert("end", f"❌ {e}\n")
            self.pipe_log.configure(state="disabled")

        run_in_thread(task, cb, ec)


    # ══════════════════════════════════════════════════
    # 🖱 集成 —— 右键菜单 + 格式竞赛 + 批量解锁
    # ══════════════════════════════════════════════════

    def _init_integrate_tab(self):
        tab = self.tab_integrate
        tab.grid_columnconfigure(0, weight=1)

        self.int_tabs = ctk.CTkTabview(tab)
        self.int_tabs.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        # ── 右键菜单 ──
        ctx = self.int_tabs.add("🖱 右键菜单")
        ctx.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(ctx, text="Windows 右键菜单集成", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=8)

        desc = ctk.CTkTextbox(ctx, height=100, state="normal")
        desc.grid(row=1, column=0, sticky="ew", padx=12, pady=4)
        desc.insert("end",
            "安装后可在文件/文件夹上右键:\n"
            "  📦 用 FluxPack 压缩 — 直接打开 GUI 并填入文件\n"
            "  📂 用 FluxPack 解压 — 自动解压到同名文件夹\n"
            "  🏆 格式竞赛 — 多格式压缩对比\n\n"
            "⚠️ 需要管理员权限运行"
        )
        desc.configure(state="disabled")

        btn_f = ctk.CTkFrame(ctx, fg_color="transparent")
        btn_f.grid(row=2, column=0, pady=8)
        self.ctx_install_btn = ctk.CTkButton(btn_f, text="✅ 安装右键菜单", command=self._do_ctx_install, fg_color="#3fb950")
        self.ctx_install_btn.pack(side="left", padx=4)
        self.ctx_uninstall_btn = ctk.CTkButton(btn_f, text="🗑 卸载右键菜单", command=self._do_ctx_uninstall, fg_color="#da3633")
        self.ctx_uninstall_btn.pack(side="left", padx=4)
        self.ctx_check_btn = ctk.CTkButton(btn_f, text="🔍 检查状态", command=self._do_ctx_check)
        self.ctx_check_btn.pack(side="left", padx=4)

        self.ctx_log = ctk.CTkTextbox(ctx, height=120, state="disabled")
        self.ctx_log.grid(row=3, column=0, sticky="ew", padx=12, pady=4)

        # ── 压缩竞赛 ──
        battle = self.int_tabs.add("🏆 压缩竞赛")
        battle.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(battle, text="用多种格式压缩同一批文件，找出最优方案", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        br = ctk.CTkFrame(battle, fg_color="transparent")
        br.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        br.grid_columnconfigure(0, weight=1)
        self.btl_src_var = ctk.StringVar()
        ctk.CTkEntry(br, textvariable=self.btl_src_var, placeholder_text="文件/文件夹路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(br, text="浏览", width=80, command=lambda: self._browse_path(self.btl_src_var)).grid(row=0, column=1)

        fmt_f = ctk.CTkFrame(battle, fg_color="transparent")
        fmt_f.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        self.btl_fmts = ["zip", "7z", "tar.gz", "tar"]
        self.btl_checks = {}
        for fmt in self.btl_fmts:
            var = ctk.BooleanVar(value=True)
            self.btl_checks[fmt] = var
            ctk.CTkCheckBox(fmt_f, text=fmt, variable=var).pack(side="left", padx=6)

        self.btl_btn = ctk.CTkButton(battle, text="🏆 开始竞赛", height=36, command=self._do_battle, fg_color="#a371f7")
        self.btl_btn.grid(row=3, column=0, pady=6)

        self.btl_log = ctk.CTkTextbox(battle, height=220, state="disabled", font=ctk.CTkFont(size=12))
        self.btl_log.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        battle.grid_rowconfigure(4, weight=1)

        # ── 批量解锁 ──
        unlock = self.int_tabs.add("🔓 批量解锁")
        unlock.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(unlock, text="批量密码解锁——字典试密码，找到后自动解压", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        ur = ctk.CTkFrame(unlock, fg_color="transparent")
        ur.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ur.grid_columnconfigure(0, weight=1)
        self.unl_arc_var = ctk.StringVar()
        ctk.CTkEntry(ur, textvariable=self.unl_arc_var, placeholder_text="加密压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(ur, text="浏览", width=80, command=lambda: self._browse_path(self.unl_arc_var)).grid(row=0, column=1)

        ur2 = ctk.CTkFrame(unlock, fg_color="transparent")
        ur2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        ur2.grid_columnconfigure(0, weight=1)
        self.unl_dict_var = ctk.StringVar()
        ctk.CTkEntry(ur2, textvariable=self.unl_dict_var, placeholder_text="字典文件路径（留空=智能候选）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(ur2, text="浏览", width=80, command=lambda: self._browse_path(self.unl_dict_var)).grid(row=0, column=1)

        self.unl_btn = ctk.CTkButton(unlock, text="🔓 开始批量解锁", height=36, command=self._do_unlock, fg_color="#da3633")
        self.unl_btn.grid(row=3, column=0, pady=6)

        self.unl_progress = ctk.CTkProgressBar(unlock)
        self.unl_progress.grid(row=4, column=0, sticky="ew", padx=8, pady=4)

        self.unl_log = ctk.CTkTextbox(unlock, height=200, state="disabled")
        self.unl_log.grid(row=5, column=0, sticky="nsew", padx=8, pady=4)
        unlock.grid_rowconfigure(5, weight=1)

        # ── 死人生成开关 ──
        dms_tab = self.int_tabs.add("⏰ 死人生成")
        dms_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(dms_tab, text="30 天不签到自动解密发送压缩包", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)

        dms_f = ctk.CTkFrame(dms_tab, fg_color="transparent")
        dms_f.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkLabel(dms_f, text="状态:").pack(side="left")
        self.dms_status_label = ctk.CTkLabel(dms_f, text="未配置", font=ctk.CTkFont(size=12))
        self.dms_status_label.pack(side="left", padx=6)

        dms_bf = ctk.CTkFrame(dms_tab, fg_color="transparent")
        dms_bf.grid(row=2, column=0, pady=6)
        ctk.CTkButton(dms_bf, text="📋 查看状态", command=self._do_dms_status).pack(side="left", padx=4)
        ctk.CTkButton(dms_bf, text="✅ 签到", command=self._do_dms_signin, fg_color="#3fb950").pack(side="left", padx=4)
        self.dms_log = ctk.CTkTextbox(dms_tab, height=200, state="disabled")
        self.dms_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        dms_tab.grid_rowconfigure(3, weight=1)

        # ── 自解压 HTML ──
        html_tab = self.int_tabs.add("📄 自解压HTML")
        html_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(html_tab, text="生成 HTML 文件，浏览器打开即可解压", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        hf1 = ctk.CTkFrame(html_tab, fg_color="transparent")
        hf1.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        hf1.grid_columnconfigure(0, weight=1)
        self.html_arc_var = ctk.StringVar()
        ctk.CTkEntry(hf1, textvariable=self.html_arc_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(hf1, text="浏览", width=80, command=lambda: self._browse_path(self.html_arc_var)).grid(row=0, column=1)
        hf2 = ctk.CTkFrame(html_tab, fg_color="transparent")
        hf2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        hf2.grid_columnconfigure(0, weight=1)
        self.html_out_var = ctk.StringVar()
        ctk.CTkEntry(hf2, textvariable=self.html_out_var, placeholder_text="输出 .html 路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(hf2, text="另存为", width=80, command=lambda: self._saveas_path(self.html_out_var)).grid(row=0, column=1)
        self.html_btn = ctk.CTkButton(html_tab, text="📄 生成自解压 HTML", command=self._do_htmlsfx)
        self.html_btn.grid(row=3, column=0, pady=6)
        self.html_log = ctk.CTkTextbox(html_tab, height=200, state="disabled")
        self.html_log.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        html_tab.grid_rowconfigure(4, weight=1)

        # ── 健康评分 ──
        score_tab = self.int_tabs.add("📊 健康评分")
        score_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(score_tab, text="给压缩包健康评分 1-100，附改进建议", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        sf = ctk.CTkFrame(score_tab, fg_color="transparent")
        sf.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        sf.grid_columnconfigure(0, weight=1)
        self.scr_path_var = ctk.StringVar()
        ctk.CTkEntry(sf, textvariable=self.scr_path_var, placeholder_text="压缩包路径").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(sf, text="浏览", width=80, command=lambda: self._browse_path(self.scr_path_var)).grid(row=0, column=1)
        self.scr_btn = ctk.CTkButton(score_tab, text="📊 评分", command=self._do_score)
        self.scr_btn.grid(row=2, column=0, pady=6)
        self.scr_log = ctk.CTkTextbox(score_tab, height=250, state="disabled")
        self.scr_log.grid(row=3, column=0, sticky="nsew", padx=8, pady=4)
        score_tab.grid_rowconfigure(3, weight=1)

        # ── 版本差异 ──
        diff_tab = self.int_tabs.add("🔄 版本差异")
        diff_tab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(diff_tab, text="像 git diff 一样对比两个压缩包", font=ctk.CTkFont(size=13)).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        df1 = ctk.CTkFrame(diff_tab, fg_color="transparent")
        df1.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        df1.grid_columnconfigure(0, weight=1)
        self.diff_a_var2 = ctk.StringVar()
        ctk.CTkEntry(df1, textvariable=self.diff_a_var2, placeholder_text="压缩包 A（旧版）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(df1, text="浏览", width=70, command=lambda: self._browse_path(self.diff_a_var2)).grid(row=0, column=1)
        df2 = ctk.CTkFrame(diff_tab, fg_color="transparent")
        df2.grid(row=2, column=0, sticky="ew", padx=8, pady=4)
        df2.grid_columnconfigure(0, weight=1)
        self.diff_b_var2 = ctk.StringVar()
        ctk.CTkEntry(df2, textvariable=self.diff_b_var2, placeholder_text="压缩包 B（新版）").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(df2, text="浏览", width=70, command=lambda: self._browse_path(self.diff_b_var2)).grid(row=0, column=1)
        self.diff_v_btn = ctk.CTkButton(diff_tab, text="🔄 对比版本", command=self._do_diff_visual)
        self.diff_v_btn.grid(row=3, column=0, pady=6)
        self.diff_v_log = ctk.CTkTextbox(diff_tab, height=250, state="disabled")
        self.diff_v_log.grid(row=4, column=0, sticky="nsew", padx=8, pady=4)
        diff_tab.grid_rowconfigure(4, weight=1)

    def _do_ctx_install(self):
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            def task():
                return install_context_menu()
            def cb(r):
                ok, msg = r
                self.ctx_log.configure(state="normal")
                self.ctx_log.delete("1.0", "end")
                self.ctx_log.insert("end", f"{'✅' if ok else '❌'} {msg}\n")
                self.ctx_log.configure(state="disabled")
            run_in_thread(task, cb)
        else:
            self.ctx_log.configure(state="normal")
            self.ctx_log.delete("1.0", "end")
            self.ctx_log.insert("end", "⏫ 需要管理员权限，正在请求 UAC 提权...\n")
            self.ctx_log.configure(state="disabled")
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable or sys.argv[0],
                "shell-install", None, 1
            )

    def _do_ctx_uninstall(self):
        def task():
            return uninstall_context_menu()

        def cb(r):
            ok, msg = r
            self.ctx_log.configure(state="normal")
            self.ctx_log.delete("1.0", "end")
            self.ctx_log.insert("end", f"{'✅' if ok else '❌'} {msg}\n")
            self.ctx_log.configure(state="disabled")

        run_in_thread(task, cb)

    def _do_ctx_check(self):
        def task():
            return check_context_menu()

        def cb(items):
            self.ctx_log.configure(state="normal")
            self.ctx_log.delete("1.0", "end")
            if not items:
                self.ctx_log.insert("end", "未找到已安装的右键菜单项\n")
            for item in items:
                status = "✅ 已安装" if item["installed"] else "❌ 未安装"
                self.ctx_log.insert("end", f"{status}: {item['name']}\n")
            self.ctx_log.configure(state="disabled")

        run_in_thread(task, cb)

    def _do_battle(self):
        src = self.btl_src_var.get()
        if not src: return
        fmts = [f for f in self.btl_fmts if self.btl_checks[f].get()]

        self.btl_btn.configure(state="disabled", text="竞赛中...")

        def task():
            return format_battle([Path(src)], formats=fmts)

        def cb(results):
            self.btl_btn.configure(state="normal", text="🏆 开始竞赛")
            self.btl_log.configure(state="normal")
            self.btl_log.delete("1.0", "end")

            if not results:
                self.btl_log.insert("end", "❌ 竞赛失败\n")
                self.btl_log.configure(state="disabled")
                return

            raw = results[0]["raw_size"] if results else 0
            self.btl_log.insert("end",
                f"🏆 压缩竞赛结果\n"
                f"原始大小: {_fmt_size(raw)}\n"
                f"{'='*55}\n"
                f"{'格式':<8} {'大小':<12} {'压缩率':>8} {'用时':>8} {'速度':>10}\n"
                f"{'-'*55}\n"
            )
            for r in results:
                mark = "🏆" if r.get("best") else "  "
                self.btl_log.insert("end",
                    f"{mark} {r['format']:<6} {r['size_fmt']:<12} {r['ratio']:>6.1f}%  {r['time']:.2f}s  {r['speed']:.1f}MB/s\n"
                )
            self.btl_log.insert("end", f"{'='*55}\n")
            best = min(results, key=lambda x: x['ratio'])
            self.btl_log.insert("end", f"🏆 推荐: {best['format']} ({best['size_fmt']}, {best['ratio']:.1f}%)\n")
            self.btl_log.configure(state="disabled")

        def ec(e):
            self.btl_btn.configure(state="normal", text="🏆 开始竞赛")
            self.btl_log.configure(state="normal")
            self.btl_log.insert("end", f"❌ {e}\n")
            self.btl_log.configure(state="disabled")

        run_in_thread(task, cb, ec)

    def _do_unlock(self):
        arc = self.unl_arc_var.get()
        if not arc: return
        dict_file = self.unl_dict_var.get()

        self.unl_btn.configure(state="disabled", text="解锁中...")
        self.unl_progress.set(0)

        def progress_cb(attempt, total, current):
            pct = attempt / total if total > 0 else 0
            self.unl_progress.set(min(pct, 0.99))

        def task():
            if dict_file:
                from src.core.power import batch_unlock_from_file
                return batch_unlock_from_file(Path(arc), Path(dict_file), progress=progress_cb)
            else:
                return unlock_with_smart_candidates(Path(arc), progress=progress_cb)

        def cb(r):
            self.unl_btn.configure(state="normal", text="🔓 开始批量解锁")
            self.unl_progress.set(1)
            self.unl_log.configure(state="normal")
            self.unl_log.delete("1.0", "end")
            if r["found"]:
                self.unl_log.insert("end",
                    f"✅ 解锁成功！密码: {r['password']}\n"
                    f"尝试 {r['attempts']} 次, 用时 {r['elapsed']:.1f}s\n"
                )
                if r["extracted_to"]:
                    self.unl_log.insert("end", f"📂 已解压到: {r['extracted_to']}\n")
            else:
                self.unl_log.insert("end",
                    f"❌ 未找到密码 (尝试 {r['attempts']} 次, 用时 {r['elapsed']:.1f}s)\n"
                )
            self.unl_log.configure(state="disabled")

        def ec(e):
            self.unl_btn.configure(state="normal", text="🔓 开始批量解锁")
            self.unl_log.configure(state="normal")
            self.unl_log.insert("end", f"❌ {e}\n")
            self.unl_log.configure(state="disabled")

        run_in_thread(task, cb, ec)


    # ── DMS 状态 ──
    def _do_dms_status(self):
        def task(): return dms_check()
        def cb(s):
            self.dms_log.configure(state="normal")
            self.dms_log.delete("1.0", "end")
            if not s.get("active"):
                self.dms_log.insert("end", "⏹ 未配置死人生成开关\n")
            elif s.get("triggered"):
                self.dms_log.insert("end", f"🚨 已触发! {s.get('triggered_at')}\n")
            else:
                self.dms_log.insert("end",
                    f"✅ 正常运行\n"
                    f"⏱ 剩余 {s['days_remaining']:.1f} 天\n"
                    f"📅 将在 {s.get('will_trigger_at', '?')} 触发\n"
                )
            self.dms_log.configure(state="disabled")
        run_in_thread(task, cb)

    def _do_dms_signin(self):
        dms_signin()
        self.dms_log.configure(state="normal")
        self.dms_log.delete("1.0", "end")
        self.dms_log.insert("end", "✅ 签到成功！倒计时已重置\n")
        self.dms_log.configure(state="disabled")

    # ── 自解压 HTML ──
    def _do_htmlsfx(self):
        arc, out = self.html_arc_var.get(), self.html_out_var.get()
        if not arc or not out: return
        self.html_btn.configure(state="disabled", text="生成中...")
        def task(): return create_self_extracting_html(Path(arc), Path(out))
        def cb(p):
            self.html_btn.configure(state="normal", text="📄 生成自解压 HTML")
            self.html_log.configure(state="normal")
            self.html_log.delete("1.0", "end")
            self.html_log.insert("end", f"✅ 已创建: {p}\n大小: {_fmt_size(p.stat().st_size)}\n对方浏览器打开即可解压\n")
            self.html_log.configure(state="disabled")
        def ec(e):
            self.html_btn.configure(state="normal", text="📄 生成自解压 HTML")
            self.html_log.configure(state="normal"); self.html_log.insert("end", f"❌ {e}\n"); self.html_log.configure(state="disabled")
        run_in_thread(task, cb, ec)

    # ── 健康评分 ──
    def _do_score(self):
        p = self.scr_path_var.get()
        if not p: return
        def task(): return score_archive(Path(p))
        def cb(r):
            self.scr_log.configure(state="normal")
            self.scr_log.delete("1.0", "end")
            grade = r.get("grade", "?")
            self.scr_log.insert("end",
                f"📊 健康评分: {grade} ({r['score']}/100)\n"
                f"{'='*40}\n"
            )
            for dim, sc in r.get("dimensions", {}).items():
                bar = "█" * (sc // 5) + "░" * ((20 - sc) // 5)
                self.scr_log.insert("end", f"{dim:<8} {bar} {sc}/20\n")
            if r.get("suggestions"):
                self.scr_log.insert("end", "\n💡 改进建议:\n")
                for s in r["suggestions"][:5]:
                    self.scr_log.insert("end", f"  • {s}\n")
            self.scr_log.configure(state="disabled")
        run_in_thread(task, cb)

    # ── 版本差异 ──
    def _do_diff_visual(self):
        a, b = self.diff_a_var2.get(), self.diff_b_var2.get()
        if not a or not b: return
        def task(): return diff_archives_visual(Path(a), Path(b))
        def cb(r):
            s = r["stats"]
            self.diff_v_log.configure(state="normal")
            self.diff_v_log.delete("1.0", "end")
            self.diff_v_log.insert("end", f"🔄 版本差异\n{'='*40}\n")
            self.diff_v_log.insert("end", f"  A: {Path(a).name} ({s['total_a']}文件)\n  B: {Path(b).name} ({s['total_b']}文件)\n\n")
            if s["added"]:
                self.diff_v_log.insert("end", f"[green]+ 新增 {s['added']}[/]\n")
                for f in r["added"][:10]:
                    self.diff_v_log.insert("end", f"  + {f['name']}\n")
            if s["removed"]:
                self.diff_v_log.insert("end", f"\n[red]- 删除 {s['removed']}[/]\n")
                for f in r["removed"][:10]:
                    self.diff_v_log.insert("end", f"  - {f['name']}\n")
            if s["changed"]:
                self.diff_v_log.insert("end", f"\n[yellow]~ 变更 {s['changed']}[/]\n")
                for c in r["changed"][:10]:
                    self.diff_v_log.insert("end", f"  ~ {c['name']} ({_fmt_size(c['size_a'])}→{_fmt_size(c['size_b'])})\n")
            self.diff_v_log.insert("end", f"\n✅ {s['unchanged']} 个相同\n")
            self.diff_v_log.configure(state="disabled")
        run_in_thread(task, cb)


# ═══════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════

def main():
    global root
    root = FluxPackApp()
    root.mainloop()


if __name__ == "__main__":
    main()
