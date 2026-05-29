"""Codex_Collector（Req 3）。

遍历 ``~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl``，逐行解析 JSONL，
提取真实 User_Prompt 并归属到项目目录 / 日期；排除被注入的上下文包装消息。

设计依据：design.md「Codex_Collector（`collectors/codex_collector.py`）— Req 3」。

JSONL 解析规则：
- 逐行 ``json.loads``；每行含顶层 ``type``。
- 首行 ``type == "session_meta"``：从 ``payload.cwd`` 读 ``project_dir``，
  从 ``payload.timestamp`` 读会话时间 → ``date``（Req 3.2）。
- User_Prompt 选取（Req 3.3）：行满足 ``type == "response_item"`` 且
  ``payload.type == "message"`` 且 ``payload.role == "user"``，其 ``payload.content``
  含 ``type == "input_text"`` 的条目，取其 ``text``。
- Injected_Context_Message 检测（Req 3.4）：候选 user 文本 ``lstrip()`` 后若以
  ``INJECTED_TAGS`` 任一标签**前缀开头**，判定为注入并排除（前缀匹配，不计入
  ``user_prompts`` 与 ``prompt_count``）。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from weekly_summary.models import CodexSession, WeekWindow

from . import CollectorWarning

__all__ = [
    "CODEX_SESSIONS_ROOT",
    "INJECTED_TAGS",
    "is_injected",
    "collect_sessions",
]

# Codex 会话日志根目录（Req 3.1）。
CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"

# 注入上下文包装标签（Req 3.4）。前缀匹配，避免误伤正文中偶然提到标签名的真实提问。
INJECTED_TAGS = (
    "<environment_context>",
    "<collaboration_mode>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "<user_instructions>",  # 兼容其它系统注入包装（前缀匹配）
)


def is_injected(text: str) -> bool:
    """判断一段 user 文本是否为 Injected_Context_Message（Req 3.4）。

    规则：``lstrip()`` 去除前导空白后，若以 :data:`INJECTED_TAGS` 任一标签
    开头则视为注入（前缀匹配）。
    """
    stripped = text.lstrip()
    return stripped.startswith(INJECTED_TAGS)


def _parse_session_timestamp(raw: object) -> datetime | None:
    """把 ``payload.timestamp`` 解析为 ``datetime``（容忍尾部 ``Z``）。"""
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.strip()
    # ISO 8601；Codex 写出形如 "2026-05-29T01:15:18.242Z" 的 UTC 时间戳。
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _extract_user_prompt(payload: dict) -> str | None:
    """从一个 ``response_item`` 的 payload 中提取真实 User_Prompt 文本。

    返回 ``None`` 表示该行不是用户提问，或是被排除的注入消息。
    """
    if payload.get("type") != "message" or payload.get("role") != "user":
        return None
    content = payload.get("content")
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for entry in content:
        if isinstance(entry, dict) and entry.get("type") == "input_text":
            text = entry.get("text")
            if isinstance(text, str):
                parts.append(text)

    if not parts:
        return None

    prompt = "".join(parts)
    if is_injected(prompt):
        return None  # Injected_Context_Message：不计入（Req 3.4）
    return prompt


def _window_contains(window: WeekWindow, moment: datetime) -> bool:
    """判断会话时间是否落在时间窗 ``[start, end]`` 内（含端点）。

    会话时间戳为 UTC（带 tzinfo），而 ``window.start/end`` 为本地时区（naive），
    故统一转换到本地 naive 时间后比较。
    """
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return window.start <= moment <= window.end


def _parse_session_file(
    path: Path, window: WeekWindow
) -> tuple[CodexSession | None, CollectorWarning | None]:
    """解析单个 rollout JSONL 文件。

    返回 ``(session, warning)``：
    - 成功且在窗内 → ``(CodexSession, None)``
    - 成功但不在窗内 → ``(None, None)``（静默跳过）
    - 解析失败 → ``(None, CollectorWarning)``（Req 3.5）
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, CollectorWarning(source=str(path), message=f"无法读取会话文件：{exc}")

    # JSONL 严格以 ``\n`` 分隔记录；只按标准换行切分，避免 ``str.splitlines()``
    # 误把 JSON 字符串里出现的 Unicode 行边界字符（U+0085 NEL、U+2028、U+2029、
    # 换页符等）当作记录分隔，从而把单条 JSON 记录错误拆成两行（导致
    # "Unterminated string" 解析失败与虚假告警）。同时兼容 ``\r\n``（去尾部 \r）。
    raw_lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]

    project_dir: str | None = None
    session_dt: datetime | None = None
    user_prompts: list[str] = []

    try:
        for line in raw_lines:
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("JSONL 行不是 JSON 对象")

            rec_type = record.get("type")
            payload = record.get("payload")

            if rec_type == "session_meta" and isinstance(payload, dict):
                cwd = payload.get("cwd")
                if isinstance(cwd, str):
                    project_dir = cwd
                session_dt = _parse_session_timestamp(payload.get("timestamp"))
            elif rec_type == "response_item" and isinstance(payload, dict):
                prompt = _extract_user_prompt(payload)
                if prompt is not None:
                    user_prompts.append(prompt)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, CollectorWarning(source=str(path), message=f"会话文件解析失败，已跳过：{exc}")

    # 缺少 session_meta（无项目目录或时间）的文件无法归属，视为不可解析并跳过。
    if project_dir is None or session_dt is None:
        return None, CollectorWarning(
            source=str(path), message="会话文件缺少 session_meta（cwd/timestamp），已跳过"
        )

    if not _window_contains(window, session_dt):
        return None, None  # 不在时间窗内，静默跳过（Req 3.1）

    session_id = _session_id_from_filename(path)
    session = CodexSession(
        session_id=session_id,
        project_dir=project_dir,
        date=_local_date(session_dt),
        user_prompts=user_prompts,
        prompt_count=len(user_prompts),  # Req 3.7
    )
    return session, None


def _local_date(moment: datetime) -> date:
    """取会话时间在本地时区的日期。"""
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment.date()


def _session_id_from_filename(path: Path) -> str:
    """从 ``rollout-<timestamp>-<uuid>.jsonl`` 文件名取 uuid 作为 session_id。

    文件名形如 ``rollout-2026-05-29T09-15-18-019e714c-c958-7080-834a-aedc21da8353``。
    uuid 为最后 5 个 ``-`` 分段拼接（标准 uuid 含 4 个连字符 → 5 段）。
    解析失败时回退到去扩展名的完整文件名。
    """
    stem = path.stem  # 去掉 .jsonl
    parts = stem.split("-")
    if len(parts) >= 5:
        return "-".join(parts[-5:])
    return stem


def collect_sessions(
    window: WeekWindow, root: Path = CODEX_SESSIONS_ROOT
) -> tuple[list[CodexSession], list[CollectorWarning]]:
    """采集时间窗内的 Codex 会话（Req 3）。

    遍历 ``root/<YYYY>/<MM>/<DD>/rollout-*.jsonl``，解析每个文件，返回落在
    ``window`` 内的 :class:`CodexSession` 列表与告警列表。

    - ``root`` 不存在 → 返回空集合 + 一条信息（Req 3.6）。
    - 单文件解析失败 → 跳过 + 告警 + 继续（Req 3.5）。
    """
    if not root.exists():
        info = CollectorWarning(
            source=str(root), message=f"Codex 会话目录不存在，跳过 Codex 采集：{root}"
        )
        return [], [info]

    sessions: list[CodexSession] = []
    warnings: list[CollectorWarning] = []

    # 稳定排序，保证结果可复现。
    for file_path in sorted(root.glob("*/*/*/rollout-*.jsonl")):
        if not file_path.is_file():
            continue
        session, warning = _parse_session_file(file_path, window)
        if warning is not None:
            warnings.append(warning)
        if session is not None:
            sessions.append(session)

    return sessions, warnings
