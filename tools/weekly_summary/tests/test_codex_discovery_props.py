"""Codex_Collector 会话文件发现与时间过滤属性测试（Task 5.4 / Property 6）。

实现 Codex_Collector 组件的 Correctness Property 6：

- **Property 6**（Req 3.1）：对在 ``~/.codex/sessions/`` 目录树下随机分布、会话时间
  在窗内 / 窗外的会话文件集合，``collect_sessions`` 应恰好读取文件名形如
  ``rollout-<timestamp>-<uuid>.jsonl`` 且会话时间落在 Week_Window 内的文件。

实现手段：在临时目录内按 ``<YYYY>/<MM>/<DD>/rollout-<timestamp>-<uuid>.jsonl`` 布局
写入会话文件，会话时间戳随机散布于 Week_Window 起点的 ±12 天（覆盖窗内与窗外）。
另混入若干**非匹配文件名**（不形如 ``rollout-*.jsonl``），断言它们被忽略。

时区稳健性：源码把 UTC 会话时间戳转换为本地时间后再与时间窗比较
（``moment.astimezone().replace(tzinfo=None)``）。本文件在断言「期望」时**以与源码
相同的方式**计算本地 naive 时间，从而避免任何 tz 边界的不确定性。

为避免 ``@given`` 与函数级 fixture（``tmp_path``）同用触发 Hypothesis 的
``function_scoped_fixture`` 健康检查，会话文件一律在每个示例内用
:func:`tempfile.TemporaryDirectory` 创建。
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import assume, given

from weekly_summary.collectors.codex_collector import collect_sessions
from weekly_summary.week_window import week_window_for

# 会话时间戳的安全年份范围（避开极端边界，使 astimezone 稳定）。
_MIN_YEAR = 2001
_MAX_YEAR = 2098


def _ts_str(dt: datetime) -> str:
    """把 UTC aware datetime 序列化为 Codex 风格的 ISO 时间戳（尾部 Z）。"""
    return dt.isoformat().replace("+00:00", "Z")


def _local_naive_of(dt_utc: datetime) -> datetime:
    """以与源码 ``_window_contains`` 相同的方式计算本地 naive 时间。"""
    return dt_utc.astimezone().replace(tzinfo=None)


def _session_meta_line(cwd: str, ts: datetime) -> str:
    return json.dumps(
        {
            "timestamp": _ts_str(ts),
            "type": "session_meta",
            "payload": {"cwd": cwd, "timestamp": _ts_str(ts)},
        },
        ensure_ascii=False,
    )


def _write_session(root: Path, ts: datetime, lines: list[str], idx: int = 0) -> Path:
    """在 ``root/<Y>/<M>/<D>/rollout-<timestamp>-<uuid>.jsonl`` 写入一个会话文件。"""
    day_dir = root / f"{ts.year:04d}" / f"{ts.month:02d}" / f"{ts.day:02d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    fname = (
        f"rollout-{ts.strftime('%Y-%m-%dT%H-%M-%S')}-{idx:04d}"
        "-aaaa-bbbb-cccc-ddddeeeeffff.jsonl"
    )
    path = day_dir / fname
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_non_matching(root: Path, ts: datetime, name: str) -> Path:
    """在日期目录下写入一个**非** ``rollout-*.jsonl`` 文件名的文件（应被忽略）。"""
    day_dir = root / f"{ts.year:04d}" / f"{ts.month:02d}" / f"{ts.day:02d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / name
    # 内容写成合法 session_meta，确保「被忽略」是文件名而非内容导致的。
    path.write_text(_session_meta_line("/should-be-ignored", ts) + "\n", encoding="utf-8")
    return path


# 非匹配文件名集合：均不形如 rollout-*.jsonl，故应被发现逻辑忽略。
_NON_MATCHING_NAMES = (
    "session.jsonl",
    "rollout-2026-05-29.txt",
    "notes.md",
    "rollout.json",
    "prefix-rollout-xxxx.jsonl",
)


@st.composite
def _discovery_plan(draw: st.DrawFn):
    """生成 ``(window, files, non_matching)``。

    - ``files``：``(marker_cwd, ts_utc)`` 列表，时间散布于窗内外。
    - ``non_matching``：``(name, ts_utc)`` 列表，文件名不形如 ``rollout-*.jsonl``。
    """
    base = draw(
        st.dates(
            min_value=datetime(_MIN_YEAR + 1, 1, 1).date(),
            max_value=datetime(_MAX_YEAR - 1, 12, 1).date(),
        )
    )
    iso = base.isocalendar()
    try:
        window = week_window_for(iso.year, iso.week)
    except ValueError:
        assume(False)

    n = draw(st.integers(min_value=1, max_value=6))
    files: list[tuple[str, datetime]] = []
    for i in range(n):
        # 相对 window.start 的秒偏移，散布于 ±12 天（覆盖窗内与窗外）。
        offset = draw(st.integers(min_value=-12 * 86400, max_value=12 * 86400))
        ts = (window.start + timedelta(seconds=offset)).replace(tzinfo=timezone.utc)
        files.append((f"/proj-{i}", ts))

    # 0~2 个非匹配文件名，时间放在窗内（确保若被错误读取会反映在断言中）。
    m = draw(st.integers(min_value=0, max_value=2))
    non_matching: list[tuple[str, datetime]] = []
    for j in range(m):
        name = draw(st.sampled_from(_NON_MATCHING_NAMES))
        # 放在窗内（周三正午），保证非匹配文件若被误读会污染结果。
        ts = (window.start + timedelta(days=2, hours=12)).replace(tzinfo=timezone.utc)
        non_matching.append((f"{j}-{name}", ts))

    return window, files, non_matching


@given(plan=_discovery_plan())
def test_property_6_session_discovery_and_time_filter(plan) -> None:
    # Feature: weekly-dev-report, Property 6: Codex 会话文件发现与时间过滤
    """**Validates: Requirements 3.1**

    ``collect_sessions`` 恰好读取 ``rollout-*.jsonl`` 且会话时间（转本地后）落在
    Week_Window 内的文件；窗外文件被静默跳过（不报错、不产生告警）；非
    ``rollout-*.jsonl`` 文件名一律被忽略。
    """
    window, files, non_matching = plan
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        expected_markers: set[str] = set()
        for i, (marker, ts) in enumerate(files):
            lines = [_session_meta_line(marker, ts)]
            _write_session(root, ts, lines, idx=i)
            # 以与源码相同的方式镜像计算「是否在窗内」，避免 tz 边界不确定性。
            local_naive = _local_naive_of(ts)
            if window.start <= local_naive <= window.end:
                expected_markers.add(marker)

        # 写入非匹配文件名（不形如 rollout-*.jsonl），它们应被忽略。
        for name, ts in non_matching:
            _write_non_matching(root, ts, name)

        sessions, warnings = collect_sessions(window, root=root)

    # 非匹配文件名不应被读取，故不会产生解析告警。
    assert warnings == []
    returned_markers = {s.project_dir for s in sessions}
    # 恰好读取窗内的 rollout-*.jsonl 文件，且不含被忽略的非匹配文件标记。
    assert returned_markers == expected_markers
    assert "/should-be-ignored" not in returned_markers
    # 无重复 / 无遗漏：发现的会话数等于窗内匹配文件数。
    assert len(sessions) == len(expected_markers)
