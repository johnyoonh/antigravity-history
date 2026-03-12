# 🔮 antigravity-history

[English](README.md) | [中文](README_zh.md)

[![PyPI Version](https://img.shields.io/pypi/v/antigravity-history)](https://pypi.org/project/antigravity-history/)
[![Python](https://img.shields.io/pypi/pyversions/antigravity-history)](https://pypi.org/project/antigravity-history/)
[![License](https://img.shields.io/github/license/neo1027144-creator/antigravity-history)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)]()

> **Export, recover, and analyze your Antigravity AI conversations — with full fidelity.**

The **only** tool that captures AI thinking chains, code diffs, command outputs, and per-message timestamps from your Antigravity sessions. Plus, recover conversations lost after crashes or updates.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🧠 **AI Thinking Process** | Export the hidden reasoning chains behind every AI response |
| 📝 **Code Diffs** | Capture every code edit with full diff context |
| 💻 **Command Outputs** | Preserve terminal outputs with exit codes and working directories |
| ⏰ **Per-Message Timestamps** | Precise timing for every message in the conversation |
| 🔄 **Conversation Recovery** | Scan `.pb` files on disk to recover conversations lost after crashes |
| 📁 **Obsidian Integration** | Export with frontmatter, tags, and `[[wiki-links]]` for your vault |
| 🖥️ **Zero-Config Discovery** | Automatically finds all running Antigravity instances |
| 🔐 **100% Local & Read-Only** | No internet, no tracking, no data modification |

---

## 🚀 Quick Start

### Install

```bash
pip install antigravity-history
```

### Export All Conversations

```bash
# Export as Markdown (default)
aghistory export

# Include AI thinking process
aghistory export --thinking

# Include everything (thinking + diffs + outputs)
aghistory export --full
```

### List Conversations

```bash
aghistory list
```

### Recover Lost Conversations

```bash
# Preview what can be recovered
aghistory recover --dry-run

# Actually recover
aghistory recover
```

### Check Status

```bash
aghistory info
```

---

## 📋 Commands

| Command | Description |
|---------|-------------|
| `aghistory export` | Export conversations to Markdown or Obsidian format |
| `aghistory list` | List all indexed conversations |
| `aghistory recover` | Recover conversations lost after crashes/updates |
| `aghistory info` | Show LanguageServer connection status |

### Export Options

| Option | Description |
|--------|-------------|
| `-o, --output DIR` | Output directory (default: `./antigravity_export`) |
| `-f, --format FMT` | Output format: `md` / `obsidian` / `all` |
| `--thinking` | Include AI's hidden reasoning process |
| `--full` | Include all extended fields (thinking + diffs + outputs) |
| `--today` | Export only today's conversations |
| `--id ID` | Export specific conversation by cascade ID |

---

## 🔒 Privacy & Security

- **100% Local** — All data stays on your machine. No internet requests.
- **Read-Only** — Never modifies, deletes, or writes to Antigravity's data.
- **No Tracking** — No analytics, telemetry, or phone-home.
- **Open Source** — Audit every line of code yourself.

---

## 🖥️ Platform Support

| Platform | Status | Discovery Method |
|----------|--------|-----------------|
| **Windows** | ✅ Supported | WMI + netstat |
| **macOS** | 🔜 Coming soon | pgrep + lsof |
| **Linux** | 🔜 Coming soon | — |

---

## ❓ FAQ

<details>
<summary><b>Does Antigravity need to be running?</b></summary>

Yes. The tool communicates with Antigravity's local LanguageServer API, which is only available while Antigravity is open with at least one workspace.
</details>

<details>
<summary><b>Will this get my account banned?</b></summary>

No. All communication is with `localhost` — no requests are sent to any external server. The tool only reads your own conversation data using the same API that Antigravity's own UI uses.
</details>

<details>
<summary><b>What are the three export levels?</b></summary>

- **Default**: User messages, AI responses, tool call summaries
- **`--thinking`**: + AI reasoning process, timestamps, exit codes
- **`--full`**: + code diffs, command outputs, search summaries, model info
</details>

<details>
<summary><b>What does "recover" do?</b></summary>

Antigravity stores conversations as `.pb` files on disk, but sometimes loses track of them in its index (e.g., after crashes or updates). The `recover` command scans these files and reloads them through the API.
</details>

<details>
<summary><b>Can I use this as a Python library?</b></summary>

Yes! You can import and use it directly in your Python code:

```python
from antigravity_history.discovery import discover_language_servers, find_all_endpoints
from antigravity_history.api import get_all_trajectories_merged, get_trajectory_steps
from antigravity_history.parser import parse_steps, FieldLevel
from antigravity_history.formatters import format_markdown, format_json
```
</details>

<details>
<summary><b>Does it support Cursor / Windsurf / other IDEs?</b></summary>

Not yet. Currently Antigravity-only. Multi-IDE support is on the roadmap.
</details>

---

## 📦 Development

```bash
git clone https://github.com/neo1027144-creator/antigravity-history
cd antigravity-history
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

---

## 📄 License

[Apache 2.0](LICENSE) — Use freely, contribute back, keep the attribution.

---

## 🌟 Star History

If this tool saved your conversations, consider giving it a ⭐!

---

<sub>**Keywords**: antigravity conversation export, antigravity chat history, export antigravity conversations, antigravity backup tool, save antigravity chat, antigravity thinking export, antigravity conversation recovery, antigravity obsidian integration, antigravity export markdown, antigravity session backup</sub>
