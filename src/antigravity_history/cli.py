"""
CLI 入口 — aghistory 命令。

子命令：
  export   导出对话为 Markdown / JSON / Obsidian
  list     列出所有对话
  recover  恢复丢失的对话
  info     显示 LanguageServer 状态
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.progress import track
except ImportError:
    print("ERROR: 缺少依赖，请运行: pip install antigravity-history")
    sys.exit(1)

from antigravity_history import __version__
from antigravity_history.discovery import (
    discover_language_servers,
    find_all_endpoints,
    find_working_endpoint,
)
from antigravity_history.api import (
    get_all_trajectories,
    get_all_trajectories_merged,
    get_trajectory_steps,
)
from antigravity_history.parser import parse_steps, FieldLevel
from antigravity_history.formatters import (
    format_markdown,
    format_json,
    format_obsidian,
    build_conversation_record,
    write_conversation,
    safe_filename,
)

app = typer.Typer(
    name="aghistory",
    help="🔮 Export, recover, and analyze your Antigravity conversations.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


def _discover_endpoints(
    port: Optional[int] = None,
    token: Optional[str] = None,
    log: Optional[Console] = None,
) -> list[dict]:
    """发现所有可用 LS 端点，失败则退出。"""
    log = log or console
    if port and token:
        log.print(f"[dim]使用手动指定: port={port}[/dim]")
        return [{"port": port, "csrf": token, "pid": 0}]

    log.print("[dim]发现 LanguageServer...[/dim]")
    servers = discover_language_servers()
    if not servers:
        err_console.print(
            "[bold red]未找到 Antigravity LanguageServer 进程。[/bold red]\n"
            "[yellow]请确认 Antigravity 正在运行，然后重试。[/yellow]"
        )
        raise typer.Exit(1)
    log.print(f"[dim]  找到 {len(servers)} 个 language_server 实例[/dim]")

    endpoints = find_all_endpoints(servers)
    if not endpoints:
        err_console.print(
            "[bold red]无法连接到任何 LanguageServer 端口。[/bold red]\n"
            "[yellow]请确认 Antigravity 正在运行且有打开的 workspace。[/yellow]"
        )
        raise typer.Exit(1)
    log.print(f"[dim]  连接到 {len(endpoints)} 个端点[/dim]")
    return endpoints


# ════════════════════════════════
# export 子命令
# ════════════════════════════════

@app.command()
def export(
    output: str = typer.Option(
        "./antigravity_export", "-o", "--output",
        help="输出目录",
    ),
    format: str = typer.Option(
        "all", "-f", "--format",
        help="输出格式: md / json / obsidian / all",
    ),
    today: bool = typer.Option(False, "--today", help="仅导出今天的对话"),
    ids: Optional[list[str]] = typer.Option(None, "--id", help="导出指定 cascade ID"),
    thinking: bool = typer.Option(False, "--thinking", help="包含 AI 思考过程"),
    full: bool = typer.Option(False, "--full", help="包含所有扩展字段 (thinking+diff+output)"),
    port: Optional[int] = typer.Option(None, "--port", help="手动指定端口"),
    token: Optional[str] = typer.Option(None, "--token", help="手动指定 CSRF Token"),
):
    """📤 导出对话为 Markdown / JSON / Obsidian 格式。"""
    # 确定字段级别
    if full:
        level = FieldLevel.FULL
    elif thinking:
        level = FieldLevel.THINKING
    else:
        level = FieldLevel.DEFAULT

    console.print(f"\n[bold]🔮 Antigravity History Export[/bold] v{__version__}")
    console.print(f"[dim]字段级别: {level}[/dim]\n")

    endpoints = _discover_endpoints(port, token)

    # 获取所有 LS 实例的对话列表（合并去重）
    console.print("[dim]获取对话列表（扫描所有 workspace）...[/dim]")
    summaries, cascade_ep = get_all_trajectories_merged(endpoints)
    console.print(f"[dim]  合并后共发现 {len(summaries)} 个对话[/dim]")

    # 指定 ID（支持未索引对话按需加载）
    default_ep = endpoints[0]
    if ids:
        for cid in ids:
            if cid not in summaries:
                summaries[cid] = {
                    "summary": f"[按需加载] {cid[:8]}...",
                    "stepCount": 1000,
                }
                cascade_ep[cid] = {"port": default_ep["port"], "csrf": default_ep["csrf"]}

    # 过滤今天
    if today:
        today_str = date.today().isoformat()
        summaries = {
            k: v for k, v in summaries.items()
            if v.get("lastModifiedTime", "").startswith(today_str)
        }
        console.print(f"[dim]  今天的对话: {len(summaries)} 个[/dim]")

    if not summaries:
        console.print("[yellow]没有找到符合条件的对话。[/yellow]")
        raise typer.Exit(0)

    # 创建输出目录
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 排序：最新的在前
    sorted_items = sorted(
        summaries.items(),
        key=lambda x: x[1].get("lastModifiedTime", ""),
        reverse=True,
    )

    # 并发获取 + 解析（线程安全的纯函数）
    def _fetch_one(cascade_id, info):
        title = info.get("summary", "Untitled")
        step_count = info.get("stepCount", 1000)
        ep = cascade_ep.get(cascade_id, {"port": default_ep["port"], "csrf": default_ep["csrf"]})
        steps = get_trajectory_steps(ep["port"], ep["csrf"], cascade_id, step_count)
        messages = parse_steps(steps, level)
        return cascade_id, title, info, messages

    # Obsidian 目录提前创建
    if format in ("obsidian", "all"):
        obs_dir = output_dir / "obsidian"
        obs_dir.mkdir(exist_ok=True)

    all_records = []
    exported_count = 0
    failed_count = 0
    MAX_WORKERS = 4

    from rich.progress import Progress
    with Progress() as progress:
        task = progress.add_task("导出中...", total=len(sorted_items))
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(_fetch_one, cid, info): cid
                for cid, info in sorted_items
            }
            for future in as_completed(futures):
                try:
                    cascade_id, title, info, messages = future.result()
                except Exception as e:
                    cid_short = futures[future][:8]
                    err_console.print(f"[red]跳过 {cid_short}...: {e}[/red]")
                    failed_count += 1
                    progress.advance(task)
                    continue

                # 写文件（主线程，不同文件无冲突）
                if format in ("md", "all"):
                    md_content = format_markdown(title, cascade_id, info, messages)
                    write_conversation(md_content, title, str(output_dir), ".md")

                if format in ("obsidian", "all"):
                    obs_content = format_obsidian(title, cascade_id, info, messages)
                    write_conversation(obs_content, title, str(obs_dir), ".md")

                if format in ("json", "all"):
                    record = build_conversation_record(cascade_id, title, info, messages)
                    all_records.append(record)

                exported_count += 1
                progress.advance(task)

    # 写 JSON
    if format in ("json", "all") and all_records:
        json_path = output_dir / "conversations_export.json"
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(format_json(all_records))

    # Obsidian 索引
    if format in ("obsidian", "all") and exported_count > 0:
        _write_obsidian_index(output_dir / "obsidian", sorted_items)

    # 摘要
    total_msgs = sum(len(r["messages"]) for r in all_records) if all_records else 0

    console.print(f"\n[bold green]✅ 导出完成！[/bold green]")
    console.print(f"  对话数: {exported_count}")
    if failed_count:
        console.print(f"  [red]失败: {failed_count}[/red]")
    if total_msgs:
        console.print(f"  消息数: {total_msgs}")
    console.print(f"  输出目录: {output_dir.absolute()}")


def _write_obsidian_index(obs_dir: Path, sorted_items):
    """生成 Obsidian 对话索引。"""
    lines = [
        "---",
        "tags: [antigravity, conversation, index]",
        f"date: {date.today().isoformat()}",
        "---",
        "",
        "# Antigravity 对话索引",
        "",
    ]
    for cascade_id, info in sorted_items:
        title = info.get("summary", "Untitled")
        modified = info.get("lastModifiedTime", "")[:10]
        step_count = info.get("stepCount", "?")
        safe = safe_filename(title)
        lines.append(f"- [[{safe}]] ({modified}, {step_count} steps)")
    
    index_path = obs_dir / "对话索引.md"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ════════════════════════════════
# list 子命令
# ════════════════════════════════

@app.command(name="list")
def list_conversations(
    limit: int = typer.Option(50, "-n", "--limit", help="最多显示条数"),
    today: bool = typer.Option(False, "--today", help="仅今天的对话"),
    json_output: bool = typer.Option(False, "--json", help="以 JSON 格式输出（管道友好）"),
    port: Optional[int] = typer.Option(None, "--port", help="手动指定端口"),
    token: Optional[str] = typer.Option(None, "--token", help="手动指定 CSRF Token"),
):
    """📋 列出所有对话。"""
    # JSON 模式下日志走 stderr，不污染 stdout
    out = err_console if json_output else console
    out.print(f"\n[bold]🔮 Antigravity Conversations[/bold]\n")

    endpoints = _discover_endpoints(port, token, log=out)
    summaries, _ = get_all_trajectories_merged(endpoints)

    if today:
        today_str = date.today().isoformat()
        summaries = {
            k: v for k, v in summaries.items()
            if v.get("lastModifiedTime", "").startswith(today_str)
        }

    sorted_items = sorted(
        summaries.items(),
        key=lambda x: x[1].get("lastModifiedTime", ""),
        reverse=True,
    )[:limit]

    if json_output:
        import json as json_mod
        records = []
        for cid, info in sorted_items:
            records.append({
                "cascade_id": cid,
                "title": info.get("summary", ""),
                "step_count": info.get("stepCount", 0),
                "last_modified": info.get("lastModifiedTime", ""),
                "created": info.get("createdTime", ""),
            })
        print(json_mod.dumps(records, indent=2, ensure_ascii=False))
    else:
        table = Table(title=f"共 {len(summaries)} 个对话")
        table.add_column("#", style="dim", width=4)
        table.add_column("最后修改", width=20)
        table.add_column("步骤", justify="right", width=6)
        table.add_column("标题", max_width=50)
        table.add_column("ID", style="dim", width=10)

        for i, (cid, info) in enumerate(sorted_items):
            t = info.get("lastModifiedTime", "?")[:19]
            table.add_row(
                str(i + 1),
                t,
                str(info.get("stepCount", "?")),
                info.get("summary", "?")[:50],
                cid[:8] + "...",
            )

        console.print(table)


# ════════════════════════════════
# recover 子命令
# ════════════════════════════════

@app.command()
def recover(
    conv_dir: str = typer.Option(
        None, "--conv-dir",
        help="conversations 目录路径 (默认: ~/.gemini/antigravity/conversations)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅检测，不执行恢复"),
    port: Optional[int] = typer.Option(None, "--port", help="手动指定端口"),
    token: Optional[str] = typer.Option(None, "--token", help="手动指定 CSRF Token"),
):
    """🔄 恢复丢失的对话（扫描 .pb 文件并通过 API 重新加载）。"""
    if conv_dir is None:
        conv_dir = os.path.expanduser("~/.gemini/antigravity/conversations")

    if not os.path.isdir(conv_dir):
        err_console.print(f"[red]目录不存在: {conv_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]🔄 Antigravity Conversation Recovery[/bold]\n")

    endpoints = _discover_endpoints(port, token)
    default_ep = endpoints[0]
    p, c = default_ep["port"], default_ep["csrf"]

    # 已索引的对话（合并所有 LS）
    indexed, _ = get_all_trajectories_merged(endpoints)
    indexed_ids = set(indexed.keys())
    console.print(f"[dim]已索引对话: {len(indexed_ids)} 个[/dim]")

    # 扫描 .pb 文件
    pb_files = sorted([f for f in os.listdir(conv_dir) if f.endswith('.pb')])
    console.print(f"[dim].pb 文件: {len(pb_files)} 个[/dim]\n")

    activated = []
    failed = []
    already_indexed = []

    for i, f in enumerate(track(pb_files, description="扫描中...")):
        cascade_id = f.replace('.pb', '')
        is_indexed = cascade_id in indexed_ids
        size_kb = os.path.getsize(os.path.join(conv_dir, f)) // 1024

        if is_indexed:
            already_indexed.append(cascade_id)
            continue

        if dry_run:
            console.print(f"  [yellow]🔍 未索引[/yellow] {cascade_id[:8]}... ({size_kb}KB)")
            continue

        # 尝试通过 API 按需加载
        result = get_trajectory_steps(p, c, cascade_id, step_count=5)
        if result:
            activated.append(cascade_id)
            console.print(f"  [green]✅ 已激活[/green] {cascade_id[:8]}... ({size_kb}KB, {len(result)}+ steps)")
        else:
            failed.append(cascade_id)
            console.print(f"  [red]❌ 失败[/red] {cascade_id[:8]}... ({size_kb}KB)")

    # 汇总
    console.print(f"\n[bold]{'─' * 40}[/bold]")
    console.print(f"  总 .pb 文件: {len(pb_files)}")
    console.print(f"  已索引: {len(already_indexed)}")
    if dry_run:
        unindexed = len(pb_files) - len(already_indexed)
        console.print(f"  未索引: {unindexed}")
        console.print(f"\n[yellow]Dry run 模式，未执行恢复。去掉 --dry-run 执行实际恢复。[/yellow]")
    else:
        console.print(f"  [green]新激活: {len(activated)}[/green]")
        if failed:
            console.print(f"  [red]失败: {len(failed)}[/red]")


# ════════════════════════════════
# info 子命令
# ════════════════════════════════

@app.command()
def info(
    port: Optional[int] = typer.Option(None, "--port", help="手动指定端口"),
    token: Optional[str] = typer.Option(None, "--token", help="手动指定 CSRF Token"),
):
    """ℹ️  显示 LanguageServer 状态信息。"""
    console.print(f"\n[bold]🔮 Antigravity History[/bold] v{__version__}\n")

    endpoints = _discover_endpoints(port, token)
    summaries, _ = get_all_trajectories_merged(endpoints)

    console.print(f"  LanguageServer 端点: {len(endpoints)} 个")
    console.print(f"  对话总数: {len(summaries)}")

    if summaries:
        # 找最新和最旧的对话
        sorted_items = sorted(
            summaries.items(),
            key=lambda x: x[1].get("lastModifiedTime", ""),
        )
        oldest = sorted_items[0][1].get("createdTime", "?")[:10]
        newest = sorted_items[-1][1].get("lastModifiedTime", "?")[:10]
        total_steps = sum(v.get("stepCount", 0) for v in summaries.values())
        console.print(f"  总步骤数: {total_steps}")
        console.print(f"  时间范围: {oldest} ~ {newest}")


# ════════════════════════════════
# version 回调
# ════════════════════════════════

def version_callback(value: bool):
    if value:
        console.print(f"antigravity-history v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v",
        callback=version_callback,
        is_eager=True,
        help="显示版本号",
    ),
):
    """🔮 Export, recover, and analyze your Antigravity conversations."""
    pass
