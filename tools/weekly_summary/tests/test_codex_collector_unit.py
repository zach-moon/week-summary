"""Codex_Collector 单元测试（Task 5.5）——基于真实 Codex JSONL fixtures。

与属性测试（``test_codex_discovery_props.py`` / ``test_codex_parse_props.py`` /
``test_codex_injected_props.py``）互补：本文件用**真实样例**的
``rollout-*.jsonl`` fixtures 覆盖具体行为与边界，聚焦三条验收标准：

- **Req 3.4（注入排除）**：解析 ``fixtures/codex/valid_session`` 下的真实会话，断言
  ``project_dir`` / ``date`` / ``user_prompts`` 正确，且被 ``<environment_context>`` /
  ``<skills_instructions>`` 等标签包裹的注入上下文消息被排除在 ``user_prompts`` 与
  ``prompt_count`` 之外。
- **Req 3.5（损坏文件跳过）**：解析 ``fixtures/codex/corrupt_session`` 下含损坏 JSON
  行的会话，断言该文件被跳过并产生一条标识该文件的告警；当损坏文件与正常文件并存于
  同一目录树时，正常文件仍被采集、损坏文件仅告警（继续处理其余文件）。
- **Req 3.6（目录缺失）**：``~/.codex/sessions/`` 目录不存在时返回空会话集合 + 一条
  说明目录缺失的信息（非致命错误，不抛异常）。

时区稳健性：会话时间戳为 UTC（带 ``Z``）。源码把它转换为本地时间后再取日期 / 比较
时间窗。本文件用一个足够宽、能覆盖任意本地时区偏移的时间窗确保 fixture 会话被发现，
并以与源码相同的方式（``astimezone().replace(tzinfo=None)``）计算期望本地日期，
从而避免任何 tz 边界的不确定性。
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from weekly_summary.collectors import CollectorWarning
from weekly_summary.collectors.codex_collector import collect_sessions
from weekly_summary.models import WeekWindow

# fixtures 根目录：tools/weekly_summary/tests/fixtures/codex/
_FIXTURES = Path(__file__).parent / "fixtures" / "codex"
_VALID_ROOT = _FIXTURES / "valid_session"
_CORRUPT_ROOT = _FIXTURES / "corrupt_session"

# 真实 fixture 会话的已知 UTC 时间戳（取自 session_meta.payload.timestamp）。
_VALID_TS = datetime(2026, 5, 29, 9, 15, 18, 242000, tzinfo=timezone.utc)
_CORRUPT_TS = datetime(2026, 5, 29, 10, 0, 0, tzinfo=timezone.utc)

# 一个足够宽的时间窗：即便本地时区偏移到 ±14h，2026-05-29 的会话也稳落其中。
_WINDOW = WeekWindow(
    start=datetime(2026, 5, 20, 0, 0, 0),
    end=datetime(2026, 6, 5, 0, 0, 0),
    report_identifier="2026-W22",
)


def _expected_local_date(ts_utc: datetime):
    """以与源码 ``_local_date`` 相同的方式计算本地日期（tz 稳健）。"""
    return ts_utc.astimezone().replace(tzinfo=None).date()


# --------------------------------------------------------------------------- #
# Req 3.4：真实样例解析 + 注入上下文消息排除
# --------------------------------------------------------------------------- #
def test_valid_fixture_parses_and_excludes_injected_messages() -> None:
    """Req 3.2/3.3/3.4/3.7：解析真实会话，排除注入上下文包装消息。

    valid_session fixture 含 5 条 user 消息：
      1. ``<environment_context>...``        → 注入，排除
      2. "帮我实现 Codex_Collector 的注入消息排除逻辑" → 真实提问，保留
      3. assistant 回复（role!=user）         → 非 user，排除
      4. "再帮我补充对应的单元测试"            → 真实提问，保留
      5. "   <skills_instructions>..."        → lstrip 后以注入标签开头，排除
    期望 ``user_prompts`` 恰为 [2, 4]，``prompt_count == 2``。
    """
    sessions, warnings = collect_sessions(_WINDOW, root=_VALID_ROOT)

    # 结构合法的真实会话：无告警，恰好一个会话。
    assert warnings == []
    assert len(sessions) == 1
    session = sessions[0]

    # Req 3.2：项目目录与日期来自 session_meta。
    assert session.project_dir == "/Users/v/Projects/week-summary"
    assert session.date == _expected_local_date(_VALID_TS)

    # Req 3.3 / 3.4：仅保留真实提问，注入上下文消息被排除。
    assert session.user_prompts == [
        "帮我实现 Codex_Collector 的注入消息排除逻辑",
        "再帮我补充对应的单元测试",
    ]

    # Req 3.7：prompt_count == len(user_prompts)。
    assert session.prompt_count == 2

    # 显式确认：任何被注入标签包裹的文本都不在 user_prompts 中。
    joined = "".join(session.user_prompts)
    assert "<environment_context>" not in joined
    assert "<skills_instructions>" not in joined


# --------------------------------------------------------------------------- #
# Req 3.5：损坏 / 不可解析的会话文件被跳过并告警
# --------------------------------------------------------------------------- #
def test_corrupt_fixture_is_skipped_with_warning() -> None:
    """Req 3.5：含损坏 JSON 行的会话文件被跳过，并产生一条标识该文件的告警。"""
    sessions, warnings = collect_sessions(_WINDOW, root=_CORRUPT_ROOT)

    # 损坏文件不产出会话。
    assert sessions == []

    # 恰好一条告警，且 source 指向该损坏文件。
    assert len(warnings) == 1
    warning = warnings[0]
    assert isinstance(warning, CollectorWarning)
    assert warning.source.endswith(
        "rollout-2026-05-29T10-00-00-aaaabbbb-cccc-dddd-eeee-ffff00001111.jsonl"
    )
    assert warning.message  # 非空、描述性


def test_corrupt_file_does_not_block_other_valid_files(tmp_path: Path) -> None:
    """Req 3.5：损坏文件与正常文件并存时，正常文件仍被采集，损坏文件仅告警并继续。

    把两个真实 fixture（valid + corrupt）复制进同一临时目录树，运行一次 collect。
    """
    valid_src = _VALID_ROOT / "2026" / "05" / "29"
    corrupt_src = _CORRUPT_ROOT / "2026" / "05" / "29"
    dest_day = tmp_path / "2026" / "05" / "29"
    dest_day.mkdir(parents=True)

    for src_dir in (valid_src, corrupt_src):
        for jsonl in src_dir.glob("rollout-*.jsonl"):
            shutil.copy2(jsonl, dest_day / jsonl.name)

    sessions, warnings = collect_sessions(_WINDOW, root=tmp_path)

    # 正常文件被采集（继续处理其余文件，未被损坏文件阻断）。
    assert len(sessions) == 1
    assert sessions[0].project_dir == "/Users/v/Projects/week-summary"
    assert sessions[0].prompt_count == 2

    # 损坏文件仅产生一条告警。
    assert len(warnings) == 1
    assert warnings[0].source.endswith(
        "rollout-2026-05-29T10-00-00-aaaabbbb-cccc-dddd-eeee-ffff00001111.jsonl"
    )


# --------------------------------------------------------------------------- #
# Req 3.6：~/.codex/sessions/ 目录缺失 → 空集合 + 一条信息（非错误）
# --------------------------------------------------------------------------- #
def test_missing_sessions_dir_returns_empty_with_info(tmp_path: Path) -> None:
    """Req 3.6：目录不存在时返回空会话集合 + 一条说明目录缺失的信息，且不抛异常。"""
    missing_root = tmp_path / "no-such-codex-sessions"
    assert not missing_root.exists()

    # 不应抛出异常（信息性、非致命）。
    sessions, warnings = collect_sessions(_WINDOW, root=missing_root)

    assert sessions == []  # 空会话集合
    assert len(warnings) == 1  # 一条信息
    info = warnings[0]
    assert isinstance(info, CollectorWarning)
    assert str(missing_root) in info.source
    assert str(missing_root) in info.message  # 信息中说明缺失的目录
