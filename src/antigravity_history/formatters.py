"""
格式化输出 — Markdown / Obsidian。

每个格式化函数接收 Conversation 数据，返回格式化后的字符串。
简单直接，不搞 ABC 抽象，后续需要再重构。
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


# ════════════════════════════════
# Markdown 格式
# ════════════════════════════════

def format_markdown(
    title: str,
    cascade_id: str,
    metadata: dict,
    messages: list[dict],
) -> str:
    """将对话格式化为 Markdown 字符串。"""
    lines = [
        f"# {title}", "",
        f"- **Cascade ID**: `{cascade_id}`",
        f"- **步骤数**: {metadata.get('stepCount', '?')}",
        f"- **创建时间**: {metadata.get('createdTime', '?')}",
        f"- **最后修改**: {metadata.get('lastModifiedTime', '?')}",
    ]

    # workspace 信息
    workspaces = metadata.get("workspaces", [])
    if workspaces:
        ws_uris = [w.get("workspaceFolderAbsoluteUri", "") for w in workspaces if w.get("workspaceFolderAbsoluteUri")]
        if ws_uris:
            lines.append(f"- **Workspace**: {', '.join(ws_uris)}")

    lines.extend([
        f"- **导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "", "---", ""
    ])

    for msg in messages:
        lines.extend(_format_message_md(msg))

    return "\n".join(lines)


def _format_message_md(msg: dict) -> list[str]:
    """格式化单条消息为 Markdown 行。"""
    role = msg.get("role", "")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")
    ts_suffix = f"  `{timestamp[:19]}`" if timestamp else ""

    lines = []

    if role == "user":
        lines.append(f"## 🧑 User{ts_suffix}")
        lines.append(content)
        lines.append("")

    elif role == "assistant":
        lines.append(f"## 🤖 Assistant{ts_suffix}")
        # thinking（如果有）
        thinking = msg.get("thinking")
        if thinking:
            lines.append("<details><summary>💭 Thinking</summary>")
            lines.append("")
            lines.append(thinking)
            lines.append("")
            lines.append("</details>")
            lines.append("")
        lines.append(content)
        # 元信息
        extras = []
        if msg.get("model"):
            extras.append(f"Model: `{msg['model']}`")
        if msg.get("stop_reason"):
            extras.append(f"Stop: `{msg['stop_reason']}`")
        if msg.get("thinking_duration"):
            extras.append(f"Think: `{msg['thinking_duration']}`")
        if extras:
            lines.append("")
            lines.append(f"*{' | '.join(extras)}*")
        lines.append("")

    elif role == "tool":
        tool_name = msg.get("tool_name", "unknown")
        lines.append(f"### 🔧 Tool: `{tool_name}`{ts_suffix}")

        if tool_name == "code_edit":
            lines.append(content)
            diff = msg.get("diff")
            if diff:
                lines.append("")
                lines.append("```diff")
                # 截断过长的 diff
                if len(diff) > 3000:
                    lines.append(diff[:3000])
                    lines.append(f"... (truncated, {len(diff)} chars total)")
                else:
                    lines.append(diff)
                lines.append("```")

        elif tool_name == "run_command":
            cwd = msg.get("cwd", "")
            exit_code = msg.get("exit_code")
            cwd_info = f" (in `{cwd}`)" if cwd else ""
            exit_info = f" → exit {exit_code}" if exit_code is not None else ""
            lines.append(f"```bash")
            lines.append(content)
            lines.append(f"```")
            if cwd_info or exit_info:
                lines.append(f"*{cwd_info}{exit_info}*")
            # 命令输出
            output = msg.get("output")
            if output:
                lines.append("")
                lines.append("<details><summary>📤 Output</summary>")
                lines.append("")
                lines.append("```")
                if len(output) > 5000:
                    lines.append(output[:5000])
                    lines.append(f"... (truncated, {len(output)} chars total)")
                else:
                    lines.append(output)
                lines.append("```")
                lines.append("")
                lines.append("</details>")

        elif tool_name == "search_web":
            lines.append(f"Query: {content}")
            search_summary = msg.get("search_summary")
            if search_summary:
                lines.append("")
                lines.append("<details><summary>🔍 Search Results</summary>")
                lines.append("")
                lines.append(search_summary)
                lines.append("")
                lines.append("</details>")

        elif tool_name == "view_file":
            num_lines = msg.get("num_lines")
            num_bytes = msg.get("num_bytes")
            size_info = ""
            if num_lines or num_bytes:
                parts = []
                if num_lines:
                    parts.append(f"{num_lines} lines")
                if num_bytes:
                    parts.append(f"{num_bytes} bytes")
                size_info = f" ({', '.join(parts)})"
            lines.append(f"`{content}`{size_info}")

        else:
            # 其他 tool 类型
            if content:
                lines.append(f"`{content[:500]}`")

        lines.append("")

    return lines


# ════════════════════════════════
# JSON 格式
# ════════════════════════════════

def format_json(conversations: list[dict]) -> str:
    """将所有对话格式化为 JSON 字符串。"""
    return json.dumps(conversations, indent=2, ensure_ascii=False)


def build_conversation_record(
    cascade_id: str,
    title: str,
    metadata: dict,
    messages: list[dict],
) -> dict:
    """构建单个对话的 JSON 记录。"""
    record = {
        "cascade_id": cascade_id,
        "title": title,
        "step_count": metadata.get("stepCount", 0),
        "created_time": metadata.get("createdTime", ""),
        "last_modified_time": metadata.get("lastModifiedTime", ""),
        "messages": messages,
    }
    workspaces = metadata.get("workspaces", [])
    if workspaces:
        ws_uris = [w.get("workspaceFolderAbsoluteUri", "")
                    for w in workspaces
                    if w.get("workspaceFolderAbsoluteUri")]
        if ws_uris:
            record["workspaces"] = ws_uris
    return record


# ════════════════════════════════
# Obsidian 格式
# ════════════════════════════════

def format_obsidian(
    title: str,
    cascade_id: str,
    metadata: dict,
    messages: list[dict],
) -> str:
    """将对话格式化为 Obsidian 兼容的 Markdown（带 frontmatter）。"""
    modified = metadata.get("lastModifiedTime", "")[:10]

    user_count = sum(1 for m in messages if m.get("role") == "user")
    ai_count = sum(1 for m in messages if m.get("role") == "assistant")

    lines = [
        "---",
        f'title: "{title}"',
        f"cascade_id: {cascade_id}",
        f"date: {modified}",
        f"messages: {len(messages)}",
        "tags: [antigravity, chat]",
        "---",
        "",
        f"# {title}",
        "",
        f"> 用户消息: {user_count} | AI 回复: {ai_count} | 总步骤: {len(messages)}",
        "",
        "---",
        "",
    ]

    for msg in messages:
        lines.extend(_format_message_md(msg))

    return "\n".join(lines)


# ════════════════════════════════
# 文件写入工具
# ════════════════════════════════

def safe_filename(title: str, max_len: int = 60) -> str:
    """将标题转换为安全文件名。"""
    return re.sub(r'[^\w\s\-]', '_', title)[:max_len].strip()


def write_conversation(
    content: str,
    title: str,
    output_dir: str,
    extension: str = ".md",
) -> str:
    """将格式化内容写入文件，返回文件路径。"""
    filename = safe_filename(title) + extension
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath
