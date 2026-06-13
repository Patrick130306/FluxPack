"""命令行接口 —— 所有功能集成"""

import sys
import time
import signal
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
)
from rich.panel import Panel
from rich.layout import Layout

from src.core.formats import open_archive, detect_format
from src.core.cracker import PasswordCracker, BUILTIN_DICT, CrackResult

console = Console()


# ── 信号处理（让 Ctrl+C 优雅退出） ─────────────────

def _signal_handler(sig, frame):
    console.print("\n[yellow]操作已取消[/]")
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)


# ── 进度回调 ─────────────────────────────────────────

def _make_cracker_callback(progress, task_id, total_estimate):
    """创建破解进度回调"""
    def callback(attempts, total, current, speed):
        progress.update(
            task_id,
            completed=attempts,
            total=total or total_estimate,
            description=f"[cyan]尝试: {attempts:,}[/] [green]{current}[/] [yellow]{speed:.0f}/s[/]"
        )
    return callback


# ═══════════════════════════════════════════════════════
# CLI 根命令
# ═══════════════════════════════════════════════════════

@click.group()
@click.version_option(version="0.2.0", prog_name="FluxPack")
def cli():
    """FluxPack — 轻量压缩包管理器

    支持 ZIP / 7Z / TAR.GZ / RAR，含密码保护、分卷、密码破解、格式转换等。
    """
    pass


# ═══════════════════════════════════════════════════════
# list — 列出压缩包内容
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--password", "-p", help="解压密码")
def list(archive_path, password):
    """列出压缩包内容"""
    path = Path(archive_path)
    try:
        archive = open_archive(path, password=password)
        entries = archive.list_contents()
    except ValueError as e:
        console.print(f"[red]❌ {e}[/]")
        sys.exit(1)

    if not entries:
        console.print("[yellow]⚠ 压缩包为空或密码错误[/]")
        return

    total_raw = sum(e.size for e in entries)
    total_comp = sum(e.compressed_size or 0 for e in entries)
    file_count = sum(1 for e in entries if not e.is_dir)

    table = Table(
        title=f"📦 [bold]{path.name}[/]  ({file_count} 个文件, {len(entries)} 条目)",
        border_style="blue"
    )
    table.add_column("文件名", style="cyan")
    table.add_column("类型", width=4)
    table.add_column("原始大小", justify="right", style="green")
    table.add_column("压缩后", justify="right", style="yellow")
    table.add_column("压缩比", justify="right")
    table.add_column("CRC", width=10)

    for entry in entries:
        entry_type = "📄" if not entry.is_dir else "📁"
        orig = _fmt_size(entry.size)
        comp = _fmt_size(entry.compressed_size) if entry.compressed_size else "-"
        ratio = f"{entry.ratio:.1%}" if entry.ratio else "-"
        crc = entry.crc or "-"
        table.add_row(entry.name, entry_type, orig, comp, ratio, crc)

    console.print(table)

    # 底部统计
    summary = (
        f"原始总大小: [green]{_fmt_size(total_raw)}[/]  →  "
        f"压缩后: [yellow]{_fmt_size(total_comp)}[/]  "
        f"({total_comp/total_raw*100:.1f}%)  "
        f"格式: [blue]{archive.format}[/]"
    )
    if archive.supports_password:
        summary += "  🔒 支持密码"
    if archive.supports_volumes:
        summary += "  📦 支持分卷"
    console.print(Panel(summary, border_style="dim"))


# ═══════════════════════════════════════════════════════
# extract — 解压
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.argument("target_dir", type=click.Path(), default=".")
@click.option("--password", "-p", help="解压密码")
@click.option("--member", "-m", multiple=True, help="仅解压指定文件（可多次使用）")
def extract(archive_path, target_dir, password, member):
    """解压到指定目录"""
    src = Path(archive_path)
    dst = Path(target_dir)
    dst.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description=f"解压 [cyan]{src.name}[/] ...", total=None)

        try:
            archive = open_archive(src, password=password)
            archive.extract(dst, members=list(member) if member else None)
            console.print(f"✅ 已解压到 [bold]{dst.resolve()}[/]")
        except ValueError as e:
            console.print(f"[red]❌ {e}[/]")
            sys.exit(1)
        except RuntimeError as e:
            console.print(f"[red]❌ {e}[/]")
            sys.exit(1)


# ═══════════════════════════════════════════════════════
# compress — 压缩
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("output", type=click.Path())
@click.argument("sources", nargs=-1, type=click.Path(exists=True))
@click.option("--format", "-f", default=None, help="强制指定格式 (zip, 7z, tar.gz)")
@click.option("--password", "-p", help="设置加密密码（仅 ZIP/7Z 支持）")
@click.option("--volume", "-v", type=int, default=None,
              help="分卷大小，单位: B/K/M/G（如 10M、1G）")
def compress(output, sources, format, password, volume):
    """压缩文件/文件夹

    支持格式: ZIP(支持AES-256加密), 7Z(支持AES-256加密), TAR.GZ, TAR

    示例:

        flux compress archive.7z file.txt folder/

        flux compress -p mypass secret.7z file.txt

        flux compress -v 10M split.zip bigfile.bin
    """
    out = Path(output)
    srcs = [Path(s) for s in sources]

    # 解析分卷大小
    volume_size = _parse_volume(volume)

    # 格式检测
    fmt = format
    if not fmt:
        try:
            fmt = detect_format(out)
        except ValueError:
            fmt = "7z"
            out = out.with_suffix(".7z")

    if password and fmt not in ("zip", "7z"):
        console.print(f"[yellow]⚠ 格式 {fmt} 不支持密码，密码已忽略[/]")

    if volume_size and fmt not in ("zip", "7z"):
        console.print(f"[yellow]⚠ 格式 {fmt} 不支持分卷，分卷已忽略[/]")

    vol_suffix = f"，分卷 {_fmt_size(volume_size)}" if volume_size else ""

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(
            description=(
                f"压缩 [cyan]{len(srcs)}[/] 个路径 → [bold]{out.name}[/]"
                f"{vol_suffix}..."
            ),
            total=None,
        )

        try:
            archive = open_archive(out, password=password)
            results = archive.compress(srcs, volume_size=volume_size)
        except NotImplementedError as e:
            console.print(f"[yellow]⚠ {e}[/]")
            sys.exit(1)

    if len(results) > 1:
        console.print(f"✅ 已创建 [bold]{len(results)}[/] 个分卷:")
        for vol in results:
            console.print(f"   [blue]{vol.name}[/] ({_fmt_size(vol.stat().st_size)})")
    else:
        console.print(f"✅ 已创建 [bold]{results[0]}[/] ({_fmt_size(results[0].stat().st_size)})")


# ═══════════════════════════════════════════════════════
# crack — 密码破解
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--method", "-m", default="smart",
              type=click.Choice(["dict", "brute", "smart", "mask"]),
              help="破解方法")
@click.option("--wordlist", "-w", type=click.Path(exists=True), help="自定义字典文件")
@click.option("--charset", "-c", default=None, help="暴力破解字符集 (如 'abcdef0123456789')")
@click.option("--min-len", type=int, default=1, help="暴力破解最小长度")
@click.option("--max-len", type=int, default=6, help="暴力破解最大长度")
@click.option("--mask", multiple=True, help="掩码模式（可多次使用，如 '?l?l?d?d'）")
@click.option("--workers", type=int, default=4, help="线程数")
def crack(archive_path, method, wordlist, charset, min_len, max_len, mask, workers):
    """破解压缩包密码

    破解方法 (--method):

        dict     字典攻击（内置300+常用密码或 --wordlist 自定义）

        brute    暴力破解（--charset, --min-len, --max-len）

        smart    智能模式：字典 → 年份 → 数字 → 字母（推荐）

        mask     掩码攻击（--mask '?l?l?d?d' 格式）

    掩码符号:

        ?l = 小写字母  ?u = 大写字母  ?d = 数字

        ?s = 特殊字符  ?a = 所有字符

    示例:

        flux crack secret.7z

        flux crack -m dict -w rockyou.txt secret.7z

        flux crack -m brute -c '0123456789' --min-len 4 --max-len 8 secret.zip

        flux crack -m mask --mask '?l?l?l?d?d' --mask '?u?l?l?l?l?d' secret.7z
    """
    path = Path(archive_path)

    # 先确认格式是否支持密码
    try:
        test = open_archive(path)
        if not test.supports_password:
            console.print(f"[yellow]⚠ 格式 {test.format} 不支持密码，不存在破解必要[/]")
            return
    except Exception:
        pass  # 可能已经有密码，正常

    cracker = PasswordCracker(path)

    console.print(f"[bold]🔓 开始破解[/] [cyan]{path.name}[/]")
    console.print(f"   文件大小: {_fmt_size(path.stat().st_size)}")
    console.print(f"   检测格式: [blue]{detect_format(path)}[/]")
    console.print()

    result = CrackResult()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            description="[yellow]初始化...[/]",
            total=1000000,
        )

        callback = _make_cracker_callback(progress, task, 1000000)

        try:
            if method == "dict":
                if wordlist:
                    result = cracker.dict_attack_from_file(Path(wordlist))
                else:
                    result = cracker.dict_attack()
            elif method == "brute":
                cs = charset or "0123456789"
                result = cracker.brute_force(cs, min_len, max_len, workers)
            elif method == "mask":
                if not mask:
                    console.print("[red]❌ 掩码攻击需要 --mask 参数[/]")
                    sys.exit(1)
                result = cracker.mask_attack(list(mask))
            else:  # smart
                result = cracker.smart_attack(workers)
        except KeyboardInterrupt:
            console.print("\n[yellow]⏹ 破解中断[/]")
            result.elapsed = time.time() - (getattr(cracker, '_start_time', time.time()))
            result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0

    console.print()
    console.print(Panel(result.summary, border_style="green" if result.found else "red"))


# ═══════════════════════════════════════════════════════
# info — 压缩包详情
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--password", "-p", help="解压密码")
def info(archive_path, password):
    """显示压缩包详细信息"""
    path = Path(archive_path)

    try:
        archive = open_archive(path, password=password)
        info_dict = archive.get_info()
    except ValueError as e:
        console.print(f"[red]❌ {e}[/]")
        sys.exit(1)

    panel = Panel.fit(
        f"[bold]📦 基本信息[/]\n"
        f"  文件名:       [cyan]{info_dict['path']}[/]\n"
        f"  格式:         [blue]{info_dict['format']}[/]\n"
        f"  大小:         {_fmt_size(info_dict['size_on_disk'])}\n"
        f"  文件数:       {info_dict['file_count']:,}\n"
        f"  目录数:       {info_dict['dir_count']:,}\n"
        f"  原始大小:     {_fmt_size(info_dict['total_raw'])}\n"
        f"  压缩后大小:   {_fmt_size(info_dict['total_compressed'])}\n"
        f"  压缩率:       {info_dict['ratio']:.1f}%\n"
        f"  支持密码:     {'✅' if archive.supports_password else '❌'}\n"
        f"  支持分卷:     {'✅' if archive.supports_volumes else '❌'}",
        title="FluxPack Archive Info",
        border_style="blue"
    )
    console.print(panel)


# ═══════════════════════════════════════════════════════
# test — 完整性校验
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--password", "-p", help="解压密码")
def test(archive_path, password):
    """校验压缩包完整性"""
    path = Path(archive_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="校验中...", total=None)

        archive = open_archive(path, password=password)
        ok, errors = archive.test_integrity()

    if ok:
        console.print(f"[bold green]✅ {path.name}[/] 完整性校验通过")
    else:
        console.print(f"[bold red]❌ {path.name}[/] 完整性校验失败:")
        for err in errors[:10]:
            console.print(f"   [red]• {err}[/]")


# ═══════════════════════════════════════════════════════
# convert — 格式转换
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("src", type=click.Path(exists=True))
@click.argument("dst", type=click.Path())
@click.option("--src-password", help="源压缩包密码")
@click.option("--dst-password", help="目标压缩包密码")
def convert(src, dst, src_password, dst_password):
    """转换压缩包格式

    示例: flux convert input.zip output.7z
    """
    src_path = Path(src)
    dst_path = Path(dst)

    from src.core.operations import convert_archive

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="转换中...", total=None)
        convert_archive(src_path, dst_path, src_password, dst_password)

    console.print(f"✅ 转换完成: [cyan]{src_path.name}[/] → [bold]{dst_path.name}[/]")


# ═══════════════════════════════════════════════════════
# batch — 批量操作
# ═══════════════════════════════════════════════════════

@cli.group()
def batch():
    """批量操作"""
    pass


@batch.command()
@click.argument("pattern", type=click.STRING)
@click.option("--output", "-o", type=click.Path(), help="输出目录")
@click.option("--password", "-p", help="解压密码")
def extract(pattern, output, password):
    """批量解压（支持通配符）

    示例: flux batch extract "*.zip"
    """
    from src.core.operations import batch_extract
    output_dir = Path(output) if output else None

    results = batch_extract(pattern, output_dir, password)
    console.print(f"✅ 批量解压完成: [cyan]{len(results)}[/] 个文件")


@batch.command()
@click.argument("pattern", type=click.STRING)
@click.option("--password", "-p", help="解压密码")
def test(pattern, password):
    """批量校验完整性

    示例: flux batch test "*.7z"
    """
    from src.core.operations import batch_test
    results = batch_test(pattern, password)

    table = Table(title="批量校验结果")
    table.add_column("文件", style="cyan")
    table.add_column("状态")
    table.add_column("详情")

    passed = 0
    for src, ok, errors in results:
        status = "[green]✅ 通过[/]" if ok else "[red]❌ 失败[/]"
        detail = errors[0] if errors else "-"
        if ok:
            passed += 1
        else:
            detail = "; ".join(errors[:2])
        table.add_row(src.name, status, detail)

    console.print(table)
    console.print(f"[bold]{passed}/{len(results)}[/] 通过")


@batch.command()
@click.argument("pattern", type=click.STRING)
@click.argument("dst_format", type=click.STRING)
@click.option("--src-password", help="源密码")
@click.option("--dst-password", help="目标密码")
def convert(pattern, dst_format, src_password, dst_password):
    """批量转换格式

    示例: flux batch convert "*.zip" 7z
    """
    from src.core.operations import batch_convert
    results = batch_convert(pattern, dst_format, src_password, dst_password)
    console.print(f"✅ 批量转换完成: [cyan]{len(results)}[/] 个文件")


# ═══════════════════════════════════════════════════════
# gui — 启动桌面 GUI
# ═══════════════════════════════════════════════════════

@cli.command()
def gui():
    """启动桌面图形界面（CustomTkinter）

    原生 Windows 桌面应用，支持所有功能：压缩/解压/浏览/破解/转换/校验。
    """
    console.print("[bold]⚡ 启动 FluxPack 桌面界面...[/]")
    console.print("   关闭终端不会影响 GUI 运行。")

    from src.ui.desktop import main as gui_main
    gui_main()


# ═══════════════════════════════════════════════════════
# shell-install / shell-uninstall — 右键菜单
# ═══════════════════════════════════════════════════════

@cli.command(name="shell-install")
def shell_install():
    """安装 Windows 右键菜单（需管理员权限）"""
    import ctypes
    # 检查是否已有管理员权限
    if ctypes.windll.shell32.IsUserAnAdmin():
        # 已有权限，直接安装
        try:
            from src.core.power import install_context_menu
            ok, msg = install_context_menu()
            if ok:
                console.print(f"[bold green]✅ {msg}[/]")
                console.print("   在文件/文件夹上右键即可看到 FluxPack 选项")
                console.print("   也可在资源管理器中使用快捷键 [bold]Alt+F[/] 压缩, [bold]Alt+E[/] 解压")
            else:
                console.print(f"[red]❌ {msg}[/]")
        except Exception as e:
            console.print(f"[red]❌ 安装失败: {e}[/]")
    else:
        # 提权重新运行
        console.print("[yellow]⏫ 需要管理员权限，正在请求 UAC 提权...[/]")
        ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable or sys.argv[0],
                "shell-install", None, 1
            )


# ═══════════════════════════════════════════════════════
# ext-register / ext-unregister — 文件关联
# ═══════════════════════════════════════════════════════

@cli.command(name="ext-register")
def ext_register():
    """注册压缩包文件关联（双击用 FluxPack 打开）"""
    import ctypes
    if ctypes.windll.shell32.IsUserAnAdmin():
        from src.core.finale import register_file_associations
        ok, msg = register_file_associations()
        if ok:
            console.print(f"[bold green]✅ {msg}[/]")
            console.print("   现在双击 .7z/.zip/.rar 等文件将用 FluxPack 打开")
        else:
            console.print(f"[red]❌ {msg}[/]")
    else:
        console.print("[yellow]⏫ 需要管理员权限，正在请求 UAC 提权...[/]")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable or sys.argv[0],
            "ext-register", None, 1
        )


# ═══════════════════════════════════════════════════════
# hashcat — GPU 加速破解
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--hashcat-path", help="hashcat.exe 路径")
@click.option("--wordlist", "-w", help="字典文件（默认6位数字掩码）")
@click.option("--hash", help="手动提供 hash（不自动提取）")
@click.option("--extra", help="额外 hashcat 参数")
def hashcat(archive_path, hashcat_path, wordlist, hash, extra):
    """使用 hashcat GPU 加速破解密码（比 Python 快 1000 万倍）"""
    from src.core.nuclear import crack_with_hashcat, HASHCAT_7Z_MODE

    if hashcat_path:
        os.environ["PATH"] = str(Path(hashcat_path).parent) + os.pathsep + os.environ.get("PATH", "")

    h = hash or ""

    with console.status("[bold green]🚀 启动 hashcat...") as status:
        result = crack_with_hashcat(
            Path(archive_path), h, wordlist=wordlist,
            extra_args=extra.split() if extra else None,
        )

    if result["error"]:
        console.print(f"[red]❌ {result['error']}[/]")
        return

    if result["found"]:
        console.print(f"[bold green]✅ 破解成功！密码: {result['password']}[/]")
        console.print(f"   ⚡ 速度: {result['speed']}")
    else:
        console.print("[yellow]❌ 未找到密码[/]")

    if result["command"]:
        console.print(f"[dim]命令: {result['command']}[/]")


# ═══════════════════════════════════════════════════════
# watch — 后台文件夹监控
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("watch_dir", type=click.Path(exists=True))
@click.option("--output", "-o", help="输出目录（默认监控目录下 _archived）")
@click.option("--format", default="7z", help="压缩格式")
@click.option("--password", "-p", help="加密密码")
@click.option("--hybrid/--no-hybrid", default=False, help="混合压缩")
@click.option("--delete/--keep", default=False, help="压缩后删除源文件")
@click.option("--interval", default=5.0, help="轮询间隔（秒）")
def watch(watch_dir, output, format, password, hybrid, delete, interval):
    """监控文件夹，新文件自动压缩归档"""
    from src.core.nuclear import ArchiveWatcher

    out = Path(output) if output else None
    profile = {"format": format, "password": password, "hybrid": hybrid}

    watcher = ArchiveWatcher(
        Path(watch_dir), output_dir=out,
        profile=profile, delete_after=delete,
        poll_interval=interval,
    )

    try:
        watcher.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]⏹ 监控已停止[/]")


# ═══════════════════════════════════════════════════════
# sfx — 自解压压缩包
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.argument("output_exe", type=click.Path())
@click.option("--extract-dir", default=".", help="解压到的子目录")
@click.option("--silent", is_flag=True, help="静默解压（无对话框）")
def sfx(archive_path, output_exe, extract_dir, silent):
    """创建自解压压缩包（双击即解压，无需任何软件）"""
    from src.core.nuclear import create_sfx_archive

    with console.status("[green]创建自解压包...") as status:
        try:
            out = create_sfx_archive(
                Path(archive_path), Path(output_exe),
                extract_dir=extract_dir, silent=silent,
            )
            console.print(f"[bold green]✅ 自解压包已创建: {out}[/]")
            console.print(f"   大小: {_fmt_size(out.stat().st_size)}")
            console.print(f"   对方双击 {out.name} 即可解压")
        except Exception as e:
            console.print(f"[red]❌ {e}[/]")


@cli.command(name="ext-unregister")
def ext_unregister():
    """卸载文件关联"""
    import ctypes
    if ctypes.windll.shell32.IsUserAnAdmin():
        from src.core.finale import unregister_file_associations
        ok, msg = unregister_file_associations()
        console.print(f"{'✅' if ok else '❌'} {msg}")
    else:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable or sys.argv[0],
            "ext-unregister", None, 1
        )


# ═══════════════════════════════════════════════════════
# dms — 死人生成开关
# ═══════════════════════════════════════════════════════

@cli.group()
def dms():
    """管理死人生成开关（定时自动发解密压缩包）"""
    pass


@dms.command(name="setup")
@click.argument("archive_path", type=click.Path(exists=True))
@click.argument("password")
@click.argument("email_to")
@click.argument("email_from")
@click.option("--smtp-server", required=True, help="SMTP 服务器")
@click.option("--smtp-port", default=587, help="SMTP 端口")
@click.option("--smtp-user", help="SMTP 用户名（默认=发件人）")
@click.option("--smtp-pass", required=True, help="SMTP 密码")
@click.option("--interval", default=30, help="间隔天数")
@click.option("--message", help="邮件正文")
def dms_setup_cmd(archive_path, password, email_to, email_from,
                  smtp_server, smtp_port, smtp_user, smtp_pass,
                  interval, message):
    """设置死人生成开关"""
    from src.core.phi import dms_setup
    config = dms_setup(
        Path(archive_path), password, email_to, email_from,
        smtp_server, smtp_port, smtp_user or email_from, smtp_pass,
        interval, message or "",
    )
    console.print("[green]✅ 死人生成开关已设置[/]")
    console.print(f"   压缩包: {config['archive']}")
    console.print(f"   间隔: {config['interval_days']} 天")
    console.print(f"   收件人: {config['email_to']}")
    console.print(f"   签到: flux dms signin")


@dms.command(name="signin")
def dms_signin_cmd():
    """签到（重置倒计时）"""
    from src.core.phi import dms_signin
    dms_signin()
    console.print("[green]✅ 签到成功！倒计时已重置[/]")


@dms.command(name="status")
def dms_status_cmd():
    """查看开关状态"""
    from src.core.phi import dms_check
    s = dms_check()
    if not s.get("active"):
        console.print(f"[yellow]{s.get('error', '未配置')}[/]")
        return
    if s.get("triggered"):
        console.print(f"[red]🚨 已触发! {s.get('triggered_at')}[/]")
    else:
        console.print(f"[green]⏱ 剩余 {s['days_remaining']:.1f} 天[/]")
        console.print(f"   最后签到: {s['last_signin']}")
        console.print(f"   将在: {s.get('will_trigger_at', '?')} 触发")


@dms.command(name="execute")
def dms_execute_cmd():
    """立即执行（解压+发邮件）"""
    from src.core.phi import dms_execute
    with console.status("[yellow]执行死人生成开关...") as status:
        r = dms_execute()
    if r.get("success"):
        console.print(f"[green]✅ 已发送到 {r.get('email_to')}[/]")
    else:
        console.print(f"[red]❌ {r.get('error', '执行失败')}[/]")


# ═══════════════════════════════════════════════════════
# htmlsfx — 自解压 HTML
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
@click.argument("output_html", type=click.Path())
@click.option("--title", default="FluxPack 自解压文件", help="页面标题")
def htmlsfx(archive_path, output_html, title):
    """创建自解压 HTML（浏览器打开即解压）"""
    from src.core.phi import create_self_extracting_html
    with console.status("[green]生成自解压 HTML...") as status:
        out = create_self_extracting_html(
            Path(archive_path), Path(output_html), title=title,
        )
    console.print(f"[green]✅ 自解压 HTML: {out}[/]")
    console.print(f"   大小: {_fmt_size(out.stat().st_size)}")
    console.print("   对方浏览器打开，点击解压即可")


# ═══════════════════════════════════════════════════════
# archive-score — 压缩健康评分
# ═══════════════════════════════════════════════════════

@cli.command(name="archive-score")
@click.argument("archive_path", type=click.Path(exists=True))
@click.option("--password", "-p")
def archive_score(archive_path, password):
    """给压缩包健康评分（1-100）"""
    from src.core.phi import score_archive

    r = score_archive(Path(archive_path), password)

    grade_colors = {"S": "green", "A": "green", "B": "yellow", "C": "red", "D": "red"}
    color = grade_colors.get(r["grade"], "white")

    console.print(f"\n[bold]📊 压缩健康评分: [{color}]{r['grade']} ({r['score']}/100)[/]")
    console.print(f"   格式: {r['details'].get('format', '?')} | "
                  f"压缩率: {r['details'].get('ratio', '?')} | "
                  f"文件: {r['details'].get('files', 0)}")

    for dim, score in r["dimensions"].items():
        bar = "█" * (score // 5) + "░" * ((20 - score) // 5)
        console.print(f"   {dim:<8} {bar} {score}/满分")

    if r["suggestions"]:
        console.print(f"\n[yellow]💡 改进建议:[/]")
        for s in r["suggestions"][:5]:
            console.print(f"   • {s}")


# ═══════════════════════════════════════════════════════
# diff-visual — 版本差异可视化
# ═══════════════════════════════════════════════════════

@cli.command(name="diff-visual")
@click.argument("archive_a", type=click.Path(exists=True))
@click.argument("archive_b", type=click.Path(exists=True))
@click.option("--password-a")
@click.option("--password-b")
def diff_visual(archive_a, archive_b, password_a, password_b):
    """可视化版本差异（类似 git diff）"""
    from src.core.phi import diff_archives_visual

    r = diff_archives_visual(Path(archive_a), Path(archive_b), password_a, password_b)
    s = r["stats"]

    console.print(f"\n[bold]🔄 版本差异对比[/]")
    console.print(f"   A: {archive_a} ({s['total_a']} 文件)")
    console.print(f"   B: {archive_b} ({s['total_b']} 文件)\n")

    if s["added"]:
        console.print(f"[green]+ 新增 {s['added']} 个文件:[/]")
        for f in r["added"][:15]:
            console.print(f"   + {f['name']} ({_fmt_size(f['size'])})")
        if s["added"] > 15:
            console.print(f"   ... 还有 {s['added']-15} 个")

    if s["removed"]:
        console.print(f"\n[red]- 删除 {s['removed']} 个文件:[/]")
        for f in r["removed"][:15]:
            console.print(f"   - {f['name']}")
        if s["removed"] > 15:
            console.print(f"   ... 还有 {s['removed']-15} 个")

    if s["changed"]:
        console.print(f"\n[yellow]~ 变更 {s['changed']} 个文件:[/]")
        for c in r["changed"][:15]:
            diff = c['diff']
            sign = "+" if diff > 0 else ""
            console.print(f"   ~ {c['name']}  ({_fmt_size(c['size_a'])} → {_fmt_size(c['size_b'])}, {sign}{_fmt_size(abs(diff))})")
        if s["changed"] > 15:
            console.print(f"   ... 还有 {s['changed']-15} 个")

    console.print(f"\n[dim]{s['unchanged']} 个文件相同[/]")


# ═══════════════════════════════════════════════════════
# xdedup — 跨格式去重
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--max", default=20, help="最大显示数")
def xdedup(directory, max):
    """跨压缩包去重检测"""
    from src.core.phi import find_cross_format_duplicates

    with console.status("[green]扫描跨格式重复...") as status:
        dups = find_cross_format_duplicates(Path(directory))

    if not dups:
        console.print("[green]✅ 未发现跨压缩包重复[/]")
        return

    total_waste = sum(d["total_wasted"] for d in dups)
    console.print(f"[yellow]🔁 发现 {len(dups)} 组跨压缩包重复[/]")
    console.print(f"   浪费空间: {_fmt_size(total_waste)}\n")

    for d in dups[:max]:
        console.print(f"📦 {d['hash'][:12]}... ({_fmt_size(d['size'])})")
        for o in d["occurrences"]:
            console.print(f"   📄 {o['archive']}/{o['path']}")
        console.print(f"   💸 浪费 {_fmt_size(d['total_wasted'])}\n")

    if len(dups) > max:
        console.print(f"... 还有 {len(dups)-max} 组")


# ═══════════════════════════════════════════════════════
# bombcheck — ZIP 炸弹检测
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("archive_path", type=click.Path(exists=True))
def bombcheck(archive_path):
    """检测压缩包是否为 ZIP 炸弹"""
    from src.core.omega import check_zip_bomb

    result = check_zip_bomb(Path(archive_path))

    if result["safe"]:
        console.print(f"[green]✅ 安全 — 压缩比 {result['ratio']:.1f}x[/]")
    else:
        for w in result["warnings"]:
            console.print(f"[red]{w}[/]")
    if result["block"]:
        console.print("[bold red]🚨 已阻止解压！这是 ZIP 炸弹[/]")


# ═══════════════════════════════════════════════════════
# pwdstrength — 密码强度评估
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("password")
def pwdstrength(password):
    """评估密码强度（hashcat 破解时间估算）"""
    from src.core.omega import estimate_crack_time
    r = estimate_crack_time(password)
    console.print(f"[bold]🔐 密码强度: {r['readable']}[/]")
    console.print(f"   长度: {r['length']} 位 | 字符集: {r['charset_size']} 种")
    console.print(f"   hashcat 7z 破解: [bold]{r['time_7z']}[/]")
    console.print(f"   hashcat ZIP 破解: [bold]{r['time_zip']}[/]")
    if r["suggestions"]:
        for s in r["suggestions"]:
            console.print(f"   [yellow]💡 {s}[/]")


# ═══════════════════════════════════════════════════════
# index — 全盘压缩包搜索
# ═══════════════════════════════════════════════════════

@cli.group()
def index():
    """管理压缩包搜索引擎"""
    pass


@index.command(name="build")
@click.argument("directory", type=click.Path(exists=True))
def index_build(directory):
    """建立压缩包文件索引"""
    from src.core.omega import build_archive_index, save_index

    with console.status("[green]🔎 扫描全盘压缩包...") as status:
        idx = build_archive_index(Path(directory))
        path = save_index(idx)

    total_files = sum(len(v) for v in idx.values())
    console.print(f"[green]✅ 索引已建立: {len(idx)} 个唯一文件名, {total_files} 条记录[/]")
    console.print(f"   索引文件: {path}")
    console.print(f"   使用: flux index search <关键词>")


@index.command(name="search")
@click.argument("keyword")
@click.option("--max", default=30, help="最大结果数")
def index_search(keyword, max):
    """在索引中搜索文件"""
    from src.core.omega import load_index, search_archive_index

    idx = load_index()
    if not idx:
        console.print("[yellow]⚠ 索引为空，请先运行: flux index build <目录>[/]")
        return

    results = search_archive_index(idx, keyword, max_results=max)

    if not results:
        console.print(f"[yellow]未找到包含「{keyword}」的文件[/]")
        return

    from rich.table import Table
    table = Table(title=f"🔎 搜索结果: {keyword} ({len(results)} 个)")
    table.add_column("文件名", style="cyan")
    table.add_column("所在压缩包", style="green")
    table.add_column("大小")
    table.add_column("压缩后")

    for r in results[:max]:
        table.add_row(
            r["path"],
            r["archive_name"],
            _fmt_size(r.get("size", 0)),
            _fmt_size(r.get("compressed_size", 0)),
        )
    console.print(table)


# ═══════════════════════════════════════════════════════
# savings — 压缩节省统计
# ═══════════════════════════════════════════════════════

@cli.command()
def savings():
    """查看压缩节省统计"""
    from src.core.omega import get_savings_summary
    s = get_savings_summary()

    from rich.table import Table
    table = Table(title="📊 压缩节省统计")
    table.add_column("指标", style="cyan")
    table.add_column("数值", style="green")

    table.add_row("累计节省", s["total_saved_fmt"])
    table.add_row("压缩文件数", str(s["total_archives"]))
    table.add_row("处理文件数", f"{s['total_files']:,}")
    table.add_row("平均压缩率", f"{s['avg_ratio']:.1f}%")
    table.add_row("今天节省", s["today_saved_fmt"])
    table.add_row("最佳日", f"{s['best_day']} ({s['best_day_saved']})")
    console.print(table)


# ═══════════════════════════════════════════════════════
# organize — 智能文件组织
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--output", "-o", help="输出目录（默认源目录下 sorted）")
@click.option("--apply", is_flag=True, help="实际执行（默认仅预览）")
def organize(directory, output, apply):
    """智能分析文件并建议组织方案"""
    from src.core.omega import suggest_organize

    files = list(Path(directory).rglob("*"))
    suggestions = suggest_organize(files)

    console.print(f"[bold]🧠 智能组织建议[/] ({len(files)} 文件)")
    for cat, items in sorted(suggestions.items()):
        console.print(f"  [cyan]{cat}[/] ({len(items)} 个)")
        for f in items[:5]:
            console.print(f"    📄 {Path(f).name}")
        if len(items) > 5:
            console.print(f"    ... 还有 {len(items)-5} 个")

    total_size = sum(f.stat().st_size for f in files if f.is_file())
    console.print(f"\n📊 总计: {len(files)} 文件, {_fmt_size(total_size)}")

    if apply:
        from src.core.omega import auto_organize
        out = Path(output) if output else Path(directory) / "sorted"
        result = auto_organize(Path(directory), out, dry_run=False)
        console.print(f"[green]✅ 已移动到: {out}[/]")
    else:
        console.print("[dim]💡 加上 --apply 实际执行[/]")


# ═══════════════════════════════════════════════════════
# honeypot — 蜜罐压缩包
# ═══════════════════════════════════════════════════════

@cli.group()
def honeypot():
    """管理蜜罐压缩包"""
    pass


@honeypot.command(name="create")
@click.argument("output", type=click.Path())
@click.option("--bait", default="密码.txt", help="诱饵文件名")
@click.option("--content", default="密码在: 管理员私信发你了", help="诱饵内容")
def honeypot_create(output, bait, content):
    """创建蜜罐压缩包"""
    from src.core.omega import create_honeypot
    out = create_honeypot(Path(output), bait_name=bait, bait_content=content)
    console.print(f"[green]✅ 蜜罐已创建: {out}[/]")
    console.print(f"   密码: [bold]123456[/] (攻击者能轻易打开)")
    console.print(f"   对方打开时会记录时间/计算机名/用户名")
    console.print(f"   查看记录: flux honeypot log")


@honeypot.command(name="log")
def honeypot_log():
    """查看蜜罐访问记录"""
    from src.core.omega import check_honeypot_log
    entries = check_honeypot_log()
    if not entries:
        console.print("[yellow]⚠ 暂无访问记录[/]")
        return
    for e in entries:
        console.print(
            f"[red]👻 蜜罐被访问![/]\n"
            f"   时间: {e['time']}\n"
            f"   计算机: {e['computer']}\n"
            f"   用户: {e['user']}\n"
            f"   IP: {e['ip']}\n"
        )


# ═══════════════════════════════════════════════════════
# profile — 压缩预设管理
# ═══════════════════════════════════════════════════════

@cli.group(name="profile")
def profile_cmd():
    """管理压缩预设"""
    pass


@profile_cmd.command(name="list")
def profile_list():
    """列出所有预设"""
    from src.core.finale import load_profiles
    profiles = load_profiles()
    console.print(f"[bold]📋 压缩预设 ({len(profiles)} 个):[/]")
    for name, p in profiles.items():
        pwd = "🔒" if p.get("password") else "  "
        vol = f" 📦{p['volume']}" if p.get("volume") else ""
        hyb = " 🧬" if p.get("hybrid") else ""
        console.print(f"  [cyan]{name}[/]  {p['format']}{pwd}{vol}{hyb}")
        console.print(f"    [dim]{p.get('desc', '')}[/]")


@profile_cmd.command(name="save")
@click.argument("name")
@click.option("--format", default="7z", help="格式")
@click.option("--password", default="", help="密码")
@click.option("--volume", default="", help="分卷大小")
@click.option("--hybrid/--no-hybrid", default=False, help="混合压缩")
@click.option("--desc", default="", help="描述")
def profile_save(name, format, password, volume, hybrid, desc):
    """保存当前参数为预设"""
    from src.core.finale import save_profile
    profile = {
        "format": format, "password": password, "volume": volume,
        "hybrid": hybrid, "level": "standard", "desc": desc,
    }
    save_profile(name, profile)
    console.print(f"[green]✅ 预设已保存: {name}[/]")


@profile_cmd.command(name="delete")
@click.argument("name")
def profile_delete(name):
    """删除预设"""
    from src.core.finale import delete_profile
    if delete_profile(name):
        console.print(f"[green]✅ 已删除: {name}[/]")
    else:
        console.print(f"[yellow]⚠ 无法删除（默认预设或不存在）: {name}[/]")


@profile_cmd.command(name="apply")
@click.argument("name")
@click.argument("output")
@click.argument("sources", nargs=-1, type=click.Path(exists=True))
@click.option("--password", "-p", help="覆盖预设密码")
def profile_apply(name, output, sources, password):
    """应用预设压缩"""
    from src.core.finale import apply_profile
    srcs = [Path(s) for s in sources]
    try:
        out = apply_profile(name, srcs, Path(output), password)
        console.print(f"[green]✅ 压缩完成: {out}[/]")
    except Exception as e:
        console.print(f"[red]❌ {e}[/]")


# ═══════════════════════════════════════════════════════
# simulate — 压缩模拟
# ═══════════════════════════════════════════════════════

@cli.command()
@click.argument("sources", nargs=-1, type=click.Path(exists=True))
@click.option("--sample", default=0.05, help="采样比例 (默认0.05=5%%)")
def simulate(sources, sample):
    """压缩模拟——采样预估各格式压缩结果"""
    from src.core.finale import simulate_compression

    srcs = [Path(s) for s in sources]

    with console.status("[bold green]采样分析中...") as status:
        results = simulate_compression(srcs, sample_ratio=sample)

    meta = results.pop("_meta", {})
    if not results:
        console.print("[yellow]⚠ 没有可分析的文件[/]")
        return

    console.print(f"\n[bold]📊 压缩模拟结果[/]")
    console.print(f"  原始: [cyan]{meta.get('total_size_fmt', '?')}[/] ({meta.get('total_files', 0)} 文件)")
    console.print(f"  采样: {meta.get('sampled_files', 0)} 文件 ({meta.get('sample_ratio', 0)*100:.0f}%)\n")

    from rich.table import Table
    table = Table(border_style="blue")
    table.add_column("格式", style="cyan")
    table.add_column("估算大小", justify="right", style="green")
    table.add_column("压缩率", justify="right")
    table.add_column("预计用时", justify="right")
    table.add_column("速度", justify="right")

    best = None
    for fmt, r in results.items():
        if "error" in r:
            table.add_row(r["label"], "❌", "", "", r["error"])
            continue
        ratio_str = f"{r['estimated_ratio']:.1f}%"
        mark = "🏆" if not best or r['estimated_ratio'] < best['estimated_ratio'] else ""
        table.add_row(
            f"{mark} {r['label']}",
            r['estimated_size_fmt'],
            ratio_str,
            r['estimated_time_fmt'],
            f"{r['speed_mbps']:.1f} MB/s"
        )
        if not best or r['estimated_ratio'] < best['estimated_ratio']:
            best = r

    console.print(table)

    if best:
        console.print(f"\n🏆 [bold]推荐: {best['label']}[/] — 约 {best['estimated_size_fmt']} ({best['estimated_ratio']:.1f}%), 预计 {best['estimated_time_fmt']}")


@cli.command(name="shell-uninstall")
def shell_uninstall():
    """卸载 Windows 右键菜单"""
    try:
        from src.core.power import uninstall_context_menu
        ok, msg = uninstall_context_menu()
        if ok:
            console.print(f"[bold green]✅ {msg}[/]")
        else:
            console.print(f"[red]❌ {msg}[/]")
    except Exception as e:
        console.print(f"[red]❌ 卸载失败: {e}[/]")


@cli.command(name="shell-check")
def shell_check():
    """检查右键菜单安装状态"""
    try:
        from src.core.power import check_context_menu
        items = check_context_menu()
        if not items:
            console.print("[yellow]⚠ 未安装任何右键菜单项[/]")
            console.print("   运行 [bold]flux shell-install[/] 安装")
        else:
            console.print("[bold]📋 右键菜单状态:[/]")
            for item in items:
                status = "[green]✅ 已安装[/]" if item["installed"] else "[red]❌ 未安装[/]"
                console.print(f"  {status} {item['name']}")
    except Exception as e:
        console.print(f"[red]❌ 检查失败: {e}[/]")


# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════

def _fmt_size(size: Optional[int]) -> str:
    """格式化文件大小"""
    if size is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"


def _parse_volume(volume_str) -> Optional[int]:
    """解析分卷大小字符串"""
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
        console.print(f"[red]❌ 无法解析分卷大小: {volume_str}[/]")
        sys.exit(1)


if __name__ == "__main__":
    cli()
