"""Property 5 专用属性测试（Task 5.3）—— 注入上下文消息被排除（关键）。

本文件按「每条属性独立一个测试文件」的约定，专门实现最高优先级的
**Property 5（Req 3.4）**：

    对任意一条 ``role=="user"`` 的消息文本，若其去除前导空白（``lstrip()``）后以某个
    注入标签（``INJECTED_TAGS``：``<environment_context>``、``<collaboration_mode>``、
    ``<skills_instructions>``、``<plugins_instructions>``、``<user_instructions>``）开头，
    则该消息被判定为 Injected_Context_Message —— 既不出现在 ``user_prompts`` 中，
    也不计入 ``prompt_count``；否则（真实提问）应被保留并计数。

验证手段（两条腿走路，力求彻底）：
1. **纯函数层**：直接对生成的字符串断言 ``is_injected(text)`` 的真值与「按构造方式确定
   的期望分类」一致——期望分类**不复用源码逻辑**，而是按生成方式判定，避免「拿被测函数
   验证自己」。
2. **端到端层**：把混合了注入 / 真实消息的多行 user 记录写入一个 Codex_Session_Log，
   经 ``collect_sessions`` 解析后断言 ``user_prompts`` 恰好等于真实消息（按序）、
   ``prompt_count == len(user_prompts)``，且任一注入文本都不在 ``user_prompts`` 中。

时区说明：会话时间戳固定取窗内一个明确的本地时刻，时间窗取足够宽的范围，使得
「文件被发现并解析」这一前提稳定成立，从而把断言聚焦在注入排除行为本身。

为避免 ``@given`` 与函数级 fixture（``tmp_path``）同用触发 Hypothesis 的
``function_scoped_fixture`` 健康检查，会话文件一律在每个示例内用
:func:`tempfile.TemporaryDirectory` 创建。
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import example, given

from weekly_summary.collectors.codex_collector import (
    INJECTED_TAGS,
    collect_sessions,
    is_injected,
)
from weekly_summary.models import WeekWindow

# 覆盖全部年份范围的「宽」时间窗：确保写入的会话文件总会被发现并解析。
_WIDE_WINDOW = WeekWindow(
    start=datetime(1990, 1, 1, 0, 0, 0),
    end=datetime(2100, 1, 1, 0, 0, 0),
    report_identifier="wide",
)

# 固定的窗内会话时间戳（UTC，带 tzinfo），避免任何午夜 / tz 边界的不确定性。
_TS = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)

# 仅由空白字符构成的前导串：lstrip() 会将其完全去除。
_leading_ws = st.text(alphabet=" \t\n\r\f\v", max_size=4)

# 安全的「首个非空白字符」：非空白且不是 "<"，从而 lstrip 后绝不可能以任何标签开头。
_safe_lead = st.sampled_from("abcdefXYZ你好0123.,!?；问")

# 任意尾串（可空）。
_tail = st.text(max_size=24)


def _ts_str(dt: datetime) -> str:
    """把 UTC aware datetime 序列化为 Codex 风格 ISO 时间戳（尾部 Z）。"""
    return dt.isoformat().replace("+00:00", "Z")


def _session_meta_line(cwd: str, ts: datetime) -> str:
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "session_meta",
            "payload": {"cwd": cwd, "timestamp": _ts_str(ts)},
        },
        ensure_ascii=False,
    )


def _user_line(ts: datetime, text: str) -> str:
    """构造一条 ``role=="user"`` 且含单个 ``input_text`` 的 response_item 行。"""
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
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


# --------------------------------------------------------------------------- #
# 生成器：(text, expected_injected)，期望分类由「构造方式」决定，不复用源码逻辑。
# --------------------------------------------------------------------------- #
@st.composite
def _classified_text(draw: st.DrawFn) -> tuple[str, bool]:
    ws = draw(_leading_ws)
    if draw(st.booleans()):
        # 注入：可选空白前缀 + 某个标签 + 任意尾串 → lstrip 后以标签开头。
        tag = draw(st.sampled_from(INJECTED_TAGS))
        return ws + tag + draw(_tail), True
    # 真实：可选空白前缀 + 安全首字符（非空白、非 "<"） + 任意尾串。
    return ws + draw(_safe_lead) + draw(_tail), False


@given(case=_classified_text())
@example(case=("<environment_context>", True))
@example(case=("<collaboration_mode>\nsome mode", True))
@example(case=("   <skills_instructions> use tools", True))
@example(case=("\t\n<plugins_instructions>x", True))
@example(case=("<user_instructions> follow", True))
@example(case=("如何在 App Router 下保护路由？", False))
@example(case=("  普通的提问，带前导空白", False))
@example(case=("<hello> 这不是注入标签", False))  # 以 "<" 开头但非注入标签
@example(case=("正文里偶然提到 <environment_context> 标签名", False))  # 非前缀
@example(case=("", False))  # 空串非注入
def test_property_5_is_injected_classification(case: tuple[str, bool]) -> None:
    # Feature: weekly-dev-report, Property 5: 注入上下文消息被排除（关键）
    """**Validates: Requirements 3.4**

    纯函数层：``is_injected(text)`` 为真当且仅当 ``text.lstrip()`` 以某个
    ``INJECTED_TAG`` 开头（前缀匹配）。期望分类按构造方式确定。
    """
    text, expected_injected = case
    assert is_injected(text) is expected_injected


@st.composite
def _session_messages(draw: st.DrawFn):
    """生成 ``(messages, expected_real)``。

    ``messages`` 为 ``(text, expected_injected)`` 列表（至少 1 条，混合注入与真实）；
    ``expected_real`` 按出现顺序仅含真实（非注入）消息的文本。
    """
    msgs = draw(st.lists(_classified_text(), min_size=1, max_size=8))
    expected_real = [text for text, injected in msgs if not injected]
    return msgs, expected_real


@given(plan=_session_messages())
def test_property_5_injected_excluded_via_collect_sessions(plan) -> None:
    # Feature: weekly-dev-report, Property 5: 注入上下文消息被排除（关键）
    """**Validates: Requirements 3.4**

    端到端层：把混合注入 / 真实的 user 消息写入一个会话文件，``collect_sessions``
    解析后 ``user_prompts`` 恰好等于真实消息（按序），``prompt_count`` 等于其数量，
    且任一注入文本都不出现在 ``user_prompts`` 中。
    """
    messages, expected_real = plan

    lines = [_session_meta_line("/proj", _TS)]
    for text, _injected in messages:
        lines.append(_user_line(_TS, text))

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        _write_session(root, _TS, lines)
        sessions, warnings = collect_sessions(_WIDE_WINDOW, root=root)

    # 结构合法的文件不应产生告警，且恰好解析出一个会话。
    assert warnings == []
    assert len(sessions) == 1
    session = sessions[0]

    # 真实提问被保留并按序计数；注入消息被排除。
    assert session.user_prompts == expected_real  # Req 3.4（保留真实）
    assert session.prompt_count == len(expected_real)  # Req 3.4 / 3.7（计数排除注入）
    for text, injected in messages:
        if injected:
            assert text not in session.user_prompts  # Req 3.4（排除注入）
