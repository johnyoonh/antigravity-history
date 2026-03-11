"""
步骤解析器 — 将 API 返回的 raw steps 解析为结构化消息。

三级字段策略：
  默认:     response, userResponse, 基础 tool calls
  thinking: + thinking, timestamp, exitCode, cwd, stopReason
  full:     + diff, combinedOutput, searchSummary, model, thinkingDuration

支持的 14 种步骤类型（10 种内容类型 + 4 种系统类型跳过）
"""

from typing import Optional


class FieldLevel:
    """字段导出级别。"""
    DEFAULT = "default"
    THINKING = "thinking"
    FULL = "full"


def parse_steps(
    steps: list[dict],
    level: str = FieldLevel.DEFAULT,
) -> list[dict]:
    """将 raw steps 解析为结构化消息列表。

    Args:
        steps: API 返回的原始步骤
        level: 字段级别 (default / thinking / full)

    Returns:
        [{"role": "user"|"assistant"|"tool", "content": str, ...}, ...]
    """
    include_thinking = level in (FieldLevel.THINKING, FieldLevel.FULL)
    include_full = level == FieldLevel.FULL

    messages = []
    for step in steps:
        step_type = step.get("type", "")
        metadata = step.get("metadata", {})
        timestamp = metadata.get("createdAt") if include_thinking else None

        msg = _parse_step(step, step_type, include_thinking, include_full)
        if msg is None:
            continue

        if timestamp:
            msg["timestamp"] = timestamp
        messages.append(msg)

    return messages


def _parse_step(
    step: dict,
    step_type: str,
    include_thinking: bool,
    include_full: bool,
) -> Optional[dict]:
    """解析单个步骤，返回消息 dict 或 None（跳过系统类型）。"""

    # ── 用户输入 ──
    if step_type == "CORTEX_STEP_TYPE_USER_INPUT":
        return _parse_user_input(step, include_full)

    # ── AI 回复（核心） ──
    if step_type == "CORTEX_STEP_TYPE_PLANNER_RESPONSE":
        return _parse_planner_response(step, include_thinking, include_full)

    # ── 代码编辑 ──
    if step_type == "CORTEX_STEP_TYPE_CODE_ACTION":
        return _parse_code_action(step, include_full)

    # ── 终端命令 ──
    if step_type == "CORTEX_STEP_TYPE_RUN_COMMAND":
        return _parse_run_command(step, include_thinking, include_full)

    # ── 文件查看 ──
    if step_type == "CORTEX_STEP_TYPE_VIEW_FILE":
        return _parse_view_file(step, include_thinking)

    # ── 文件搜索 ──
    if step_type == "CORTEX_STEP_TYPE_FIND":
        find = step.get("find", {})
        return {"role": "tool", "tool_name": "find", "content": find.get("query", "[File Search]")}

    # ── 目录列表 ──
    if step_type == "CORTEX_STEP_TYPE_LIST_DIRECTORY":
        ld = step.get("listDirectory", {})
        path = ld.get("directoryPath", ld.get("path", ""))
        return {"role": "tool", "tool_name": "list_dir", "content": path or "[List Directory]"}

    # ── 网页搜索 ──
    if step_type == "CORTEX_STEP_TYPE_SEARCH_WEB":
        return _parse_search_web(step, include_full)

    # ── URL 内容读取 ──
    if step_type == "CORTEX_STEP_TYPE_READ_URL_CONTENT":
        ru = step.get("readUrlContent", {})
        return {"role": "tool", "tool_name": "read_url", "content": ru.get("url", "[Read URL]")}

    # ── 命令状态检查 ──
    if step_type == "CORTEX_STEP_TYPE_COMMAND_STATUS":
        return {"role": "tool", "tool_name": "command_status", "content": "[Check Command Status]"}

    # ── 系统类型：跳过 ──
    # EPHEMERAL_MESSAGE, CONVERSATION_HISTORY, CHECKPOINT, KNOWLEDGE_ARTIFACTS, ERROR_MESSAGE
    return None


# ─────────────────────────────────
# 各类型的详细解析
# ─────────────────────────────────

def _parse_user_input(step: dict, include_full: bool) -> Optional[dict]:
    ui = step.get("userInput", {})
    content = ui.get("userResponse", "")
    if not content:
        return None

    msg = {"role": "user", "content": content}

    if include_full:
        # 编辑器状态（仅 full 模式）
        state = ui.get("activeUserState", {})
        active_doc = state.get("activeDocument", {})
        if active_doc.get("absoluteUri"):
            msg["active_file"] = active_doc["absoluteUri"]
            msg["editor_language"] = active_doc.get("editorLanguage", "")

    return msg


def _parse_planner_response(
    step: dict, include_thinking: bool, include_full: bool
) -> Optional[dict]:
    pr = step.get("plannerResponse", {})
    # 优先 modifiedResponse（后处理版本），否则用 response
    content = pr.get("modifiedResponse") or pr.get("response", "")
    if not content:
        return None

    msg = {"role": "assistant", "content": content}

    # thinking 级别：加入推理链、停止原因
    if include_thinking:
        thinking = pr.get("thinking")
        if thinking:
            msg["thinking"] = thinking
        stop_reason = pr.get("stopReason")
        if stop_reason:
            msg["stop_reason"] = stop_reason

    # full 级别：加入模型名、思考耗时、消息ID
    if include_full:
        metadata = step.get("metadata", {})
        model = metadata.get("generatorModel")
        if model:
            msg["model"] = model
        thinking_duration = pr.get("thinkingDuration")
        if thinking_duration:
            msg["thinking_duration"] = thinking_duration
        message_id = pr.get("messageId")
        if message_id:
            msg["message_id"] = message_id

    return msg


def _parse_code_action(step: dict, include_full: bool) -> Optional[dict]:
    ca = step.get("codeAction", {})
    description = ca.get("description", "")

    # 文件路径：优先 actionResult，其次 actionSpec
    file_path = ""
    action_result = ca.get("actionResult", {})
    edit = action_result.get("edit", {})
    if edit.get("absoluteUri"):
        file_path = edit["absoluteUri"]
    elif ca.get("actionSpec", {}).get("createFile", {}).get("path"):
        file_path = ca["actionSpec"]["createFile"]["path"]

    summary = f"[Code Edit] {file_path}" if file_path else "[Code Edit]"
    if description:
        summary += f"\n{description}"

    msg = {"role": "tool", "tool_name": "code_edit", "content": summary}

    if file_path:
        msg["file_path"] = file_path

    # full 模式：包含 diff
    if include_full:
        diff = edit.get("diff")
        if diff:
            msg["diff"] = diff
        # artifact 元数据
        artifact = ca.get("artifactMetadata", {})
        if artifact.get("summary"):
            msg["artifact_summary"] = artifact["summary"]
        if artifact.get("artifactType"):
            msg["artifact_type"] = artifact["artifactType"]
        is_artifact = ca.get("isArtifactFile")
        if is_artifact:
            msg["is_artifact"] = True

    return msg


def _parse_run_command(
    step: dict, include_thinking: bool, include_full: bool
) -> Optional[dict]:
    rc = step.get("runCommand", {})
    command = rc.get("commandLine", rc.get("command", ""))
    if not command:
        return None

    msg = {"role": "tool", "tool_name": "run_command", "content": command}

    # thinking 级别：工作目录、退出码
    if include_thinking:
        cwd = rc.get("cwd")
        if cwd:
            msg["cwd"] = cwd
        exit_code = rc.get("exitCode")
        if exit_code is not None:
            msg["exit_code"] = exit_code

    # full 级别：命令完整输出
    if include_full:
        output = rc.get("combinedOutput", {}).get("full")
        if output:
            msg["output"] = output

    return msg


def _parse_view_file(step: dict, include_thinking: bool) -> Optional[dict]:
    vf = step.get("viewFile", {})
    path = vf.get("absolutePathUri", vf.get("filePath", vf.get("path", "")))
    if not path:
        return None

    msg = {"role": "tool", "tool_name": "view_file", "content": path}

    # thinking 级别：文件大小信息
    if include_thinking:
        num_lines = vf.get("numLines")
        num_bytes = vf.get("numBytes")
        if num_lines:
            msg["num_lines"] = num_lines
        if num_bytes:
            msg["num_bytes"] = num_bytes

    # 注意：永远不导出 viewFile.content（文件完整内容，太大且冗余）
    return msg


def _parse_search_web(step: dict, include_full: bool) -> Optional[dict]:
    sw = step.get("searchWeb", {})
    query = sw.get("query", "")

    msg = {"role": "tool", "tool_name": "search_web", "content": query or "[Web Search]"}

    # full 级别：搜索结果完整摘要（~7KB）
    if include_full:
        summary = sw.get("summary")
        if summary:
            msg["search_summary"] = summary
        provider = sw.get("thirdPartyConfig", {}).get("provider")
        if provider:
            msg["search_provider"] = provider

    return msg
