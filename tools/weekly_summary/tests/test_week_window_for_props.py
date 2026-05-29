"""Week_Window 指定周时间窗属性测试（Task 3.3 / Property 8）。

实现 Week_Window 组件的 Correctness Property 8：

- **Property 8**（Req 4.2）：对任意合法的 ``(year, iso_week)``，
  ``week_window_for(year, iso_week)`` 给出该周周一 00:00:00 至周日 23:59:59
  （本地时区），窗跨度约 7 天，且 ``report_identifier`` 为
  ``f"{year}-W{iso_week:02d}"``。

ISO 周的合法性约束：并非每个 ``(year, week)`` 组合都合法（短年份没有第 53 周）。
生成器用 :func:`datetime.date.fromisocalendar` 试探合法性，非法组合用
:func:`hypothesis.assume` 跳过。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import hypothesis.strategies as st
from hypothesis import assume, given

from weekly_summary.week_window import week_window_for

# 年份范围约 1900–2100（naive 本地 datetime / date）。
_MIN_YEAR = 1900
_MAX_YEAR = 2100


@st.composite
def _valid_iso_week(draw: st.DrawFn) -> tuple[int, int]:
    """生成合法的 ``(year, iso_week)``；非法组合（如短年份的第 53 周）被跳过。"""
    year = draw(st.integers(min_value=_MIN_YEAR, max_value=_MAX_YEAR))
    iso_week = draw(st.integers(min_value=1, max_value=53))
    try:
        date.fromisocalendar(year, iso_week, 1)
    except ValueError:
        assume(False)  # 该年没有这一周（仅可能发生在 week == 53）。
    return year, iso_week


@given(case=_valid_iso_week())
def test_property_8_week_window_for_specified_week(case: tuple[int, int]) -> None:
    # Feature: weekly-dev-report, Property 8: 指定周 Week_Window 计算
    """**Validates: Requirements 4.2**

    ``week_window_for(year, iso_week)`` 的 ``start`` 应为该周周一 00:00:00、
    ``end`` 应为该周周日 23:59:59（本地时区），窗跨度约 7 天，且
    ``report_identifier`` 为 ``f"{year}-W{iso_week:02d}"``。
    """
    year, iso_week = case
    window = week_window_for(year, iso_week)

    monday = date.fromisocalendar(year, iso_week, 1)
    sunday = date.fromisocalendar(year, iso_week, 7)

    # start：周一 00:00:00。
    assert window.start == datetime.combine(monday, time(0, 0, 0))
    assert window.start.weekday() == 0
    assert window.start.time() == time(0, 0, 0)

    # end：周日 23:59:59。
    assert window.end == datetime.combine(sunday, time(23, 59, 59))
    assert window.end.weekday() == 6
    assert window.end.time() == time(23, 59, 59)

    # 窗跨度约 7 天：Monday 00:00:00 → Sunday 23:59:59 = 6 天 23:59:59。
    assert window.end - window.start == timedelta(days=6, hours=23, minutes=59, seconds=59)

    # report_identifier 与指定周一致。
    assert window.report_identifier == f"{year}-W{iso_week:02d}"
