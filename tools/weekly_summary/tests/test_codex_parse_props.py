"""Codex_Collector 会话解析属性测试（Task 5.2 / Property 4）。

实现 Codex_Collector 的 **Property 4（Codex 会话解析正确性）**：

- **Property 4**（Req 3.2、3.3、3.7）：对一个结构合法的 Codex_Session_Log（随机
  ``session_meta`` 的 ``cwd`` / ``timestamp`` 与随机混合行），``collect_sessions``
  解析出的会话的 ``project_dir`` 与 ``date`` 应分别等于 ``payload.cwd`` 与
  ``payload.timestamp``（取本地日期）；其 ``user_prompts`` 应恰好包含所有满足
  ``type == "response_item"``、``payload.type == "message"``、``payload.role == "user"``、
  含 ``input_text`` 且非注入的条目（按出现顺序）；且 ``prompt_count == len(user_prompts)``。

时区稳健性：源码把 UTC 会话时间戳转换为本地时间后再取日期
（``moment.astimezone().replace(tzinfo=None)``）。本文件以与源码相同的方式计算期望
的本地日期，避免任何 tz 边界的不确定性；并使用足够宽的时间窗，仅断言「会话被发现
并解析」，不依赖具体午夜边界。

为避免 ``@given`` 与函数级 fixture（``tmp_path``）同用触发 Hypothesis 的
``function_scoped_fixture`` 健康检查，会话文件一律在每个示例内用
:func:`tempfile.TemporaryDirectory` 创建。
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given, settings

from weekly_summary.collectors.codex_collector import (
    INJECTED_TAGS,
    collect_sessions,
)
from weekly_summary.models import WeekWindow

# 会话时间戳的安全年份范围（避开极端边界，使 astimezone 稳定）。
_MIN_YEAR = 2001
_MAX_YEAR = 2098

# 覆盖全部年份范围的「宽」时间窗，确保任意会话时间戳都落在窗内、总被发现。
_WIDE_WINDOW = WeekWindow(
    start=datetime(1990, 1, 1, 0, 0, 0),
    end=datetime(2100, 1, 1, 0, 0, 0),
    report_identifier="wide",
)

# 生成 UTC（带 tzinfo）会话时间戳。
_utc_datetimes = st.datetimes(
    min_value=datetime(_MIN_YEAR, 1, 1, 0, 0, 0),
    max_value=datetime(_MAX_YEAR, 12, 31, 23, 59, 59),
    timezones=st.just(timezone.utc),
)

# 非注入 user 文本：首个非空白字符不是 "<"，从而 lstrip 后不可能以任何标签开头。
_safe_lead = st.sampled_from("abcXYZ你好0123.,!?；问")
_non_injected_text = st.builds(
    lambda lead, body: lead + body,
    _safe_lead,
    st.text(max_size=20),
)

# 注入 user 文本：可选前导空白 + 某个标签 + 任意尾串 → lstrip 后以标签开头。
_injected_text = st.builds(
    lambda ws, tag, tail: ws + tag + tail,
    st.text(alphabet=" \t\n\r", max_size=3),
    st.sampled_from(INJECTED_TAGS),
    st.text(max_size=20),
)

# 会话项目目录（cwd）：非空、类路径字符串。
_cwd_text = st.builds(
    lambda body: "/" + body,
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/",
        min_size=1,
        max_size=24,
    ),
)


def _ts_str(dt: datetime) -> str:
    """把 UTC aware datetime 序列化为 Codex 风格的 ISO 时间戳（尾部 Z）。"""
    return dt.isoformat().replace("+00:00", "Z")


def _local_date_of(dt_utc: datetime) -> date:
    """以与源码 ``_local_date`` 相同的方式计算本地日期。"""
    return dt_utc.astimezone().replace(tzinfo=None).date()


def _session_meta_line(cwd: str, ts: datetime) -> str:
    """首行 session_meta：携带 payload.cwd 与 payload.timestamp。"""
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "session_meta",
            "payload": {"cwd": cwd, "timestamp": _ts_str(ts)},
        },
        ensure_ascii=False,
    )


def _user_line(ts: datetime, texts: list[str]) -> str:
    """response_item / message / role==user，含若干 input_text 内容条目。"""
    content = [{"type": "input_text", "text": t} for t in texts]
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": content},
        },
        ensure_ascii=False,
    )


def _assistant_line(ts: datetime, text: str) -> str:
    """response_item / message / role==assistant（噪声，应被排除）。"""
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        },
        ensure_ascii=False,
    )


def _event_line(ts: datetime) -> str:
    """event_msg 行（噪声，应被排除）。"""
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "event_msg",
            "payload": {"type": "token_count", "info": {"total_tokens": 1}},
        },
        ensure_ascii=False,
    )


def _user_no_text_line(ts: datetime) -> str:
    """role==user 的消息，但内容不含 input_text（应被排除）。"""
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "output_text", "text": "noise"}],
            },
        },
        ensure_ascii=False,
    )


def _user_reasoning_line(ts: datetime) -> str:
    """response_item 但 payload.type != "message"（应被排除）。"""
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "response_item",
            "payload": {"type": "reasoning", "role": "user", "summary": "x"},
        },
        ensure_ascii=False,
    )


def _write_session(root: Path, ts: datetime, lines: list[str], idx: int = 0) -> Path:
    """在 ``root/<Y>/<M>/<D>/rollout-<...>-<uuid>.jsonl`` 写入一个会话文件。"""
    day_dir = root / f"{ts.year:04d}" / f"{ts.month:02d}" / f"{ts.day:02d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    fname = (
        f"rollout-{ts.strftime('%Y-%m-%dT%H-%M-%S')}-{idx:04d}"
        "-aaaa-bbbb-cccc-ddddeeeeffff.jsonl"
    )
    path = day_dir / fname
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@st.composite
def _session_plan(draw: st.DrawFn):
    """生成 ``(cwd, ts, lines, expected_prompts)``。

    首行为 session_meta；其后混入 real / injected user 消息与 assistant / event /
    无 input_text 的 user / 非 message 的 response_item 等噪声行。``expected_prompts``
    按出现顺序仅含 real（非注入）user 消息拼接后的文本。
    """
    cwd = draw(_cwd_text)
    ts = draw(_utc_datetimes)
    lines = [_session_meta_line(cwd, ts)]
    expected: list[str] = []

    n = draw(st.integers(min_value=0, max_value=6))
    for _ in range(n):
        kind = draw(
            st.sampled_from(
                ["real", "injected", "assistant", "event", "user_no_text", "user_reasoning"]
            )
        )
        if kind == "real":
            parts = draw(st.lists(_non_injected_text, min_size=1, max_size=2))
            lines.append(_user_line(ts, parts))
            expected.append("".join(parts))
        elif kind == "injected":
            lines.append(_user_line(ts, [draw(_injected_text)]))
        elif kind == "assistant":
            lines.append(_assistant_line(ts, draw(st.text(max_size=10))))
        elif kind == "event":
            lines.append(_event_line(ts))
        elif kind == "user_no_text":
            lines.append(_user_no_text_line(ts))
        else:  # user_reasoning
            lines.append(_user_reasoning_line(ts))

    return cwd, ts, lines, expected


@settings(max_examples=100, deadline=None)
@given(plan=_session_plan())
def test_property_4_codex_session_parsing(plan) -> None:
    # Feature: weekly-dev-report, Property 4: Codex 会话解析正确性
    """**Validates: Requirements 3.2, 3.3, 3.7**

    ``project_dir`` 等于 ``payload.cwd``；``date`` 等于 ``payload.timestamp`` 的本地
    日期；``user_prompts`` 恰好为非注入的真实 user input_text（按序）；
    ``prompt_count == len(user_prompts)``。
    """
    cwd, ts, lines, expected = plan
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        _write_session(root, ts, lines)
        sessions, warnings = collect_sessions(_WIDE_WINDOW, root=root)

    # 结构合法的文件不应产生告警，且恰好解析出一个会话。
    assert warnings == []
    assert len(sessions) == 1
    session = sessions[0]

    assert session.project_dir == cwd  # Req 3.2
    assert session.date == _local_date_of(ts)  # Req 3.2（本地日期）
    assert session.user_prompts == expected  # Req 3.3
    assert session.prompt_count == len(expected)  # Req 3.7
