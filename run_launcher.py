"""FluxPack 启动器 — 无参数→GUI / 有参数→CLI / 文件路径→打开 / 拖拽→快速压缩"""
import sys
import os

# Windows GBK 兼容
if sys.platform == "win32":
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except: pass
    os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CLI_COMMANDS = {
    "compress", "extract", "list", "info", "crack", "test",
    "convert", "batch", "gui", "shell-install", "shell-uninstall",
    "shell-check", "ext-register", "ext-unregister",
    "profile", "simulate",
}


def main():
    args = sys.argv[1:]

    # 无参数 → GUI
    if not args:
        from src.ui.desktop import main as gui_main
        gui_main()
        return

    first = args[0].lower()

    # CLI 命令 → 走命令行
    if first in CLI_COMMANDS or first.startswith("--"):
        from src.ui.cli import cli
        cli()
        return

    # open 子命令 → 用 GUI 打开压缩包
    if first == "open" and len(args) >= 2:
        filepath = args[1]
        from src.ui.desktop import FluxPackApp
        import customtkinter as ctk
        root = ctk.CTk()
        app = FluxPackApp()
        app.tabview.set("📋 浏览")
        app.brs_path_var.set(filepath)
        app._do_browse()
        root.mainloop()
        return

    # 文件路径（拖拽或双击打开）→ 预填到 GUI 压缩页
    files = [a for a in args if os.path.isfile(a) or os.path.isdir(a)]
    if files:
        from src.ui.desktop import FluxPackApp
        import customtkinter as ctk
        root = ctk.CTk()
        app = FluxPackApp()
        app.tabview.set("📦 压缩")
        app._cmp_sources = files
        app._update_src_list()
        root.mainloop()
        return

    # 都不是 → 当 CLI 处理
    from src.ui.cli import cli
    cli()


if __name__ == "__main__":
    main()
