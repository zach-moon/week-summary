"""默认 Week_Window 属性测试（Task 3.2 / Property 7）。

实现 Week_Window 组件「默认时间窗」的 Correctness Property：

- **Property 7**（Req 4.1）：对任意当前时刻 ``now``，``current_week_window(now)``
  的 ``start`` 应等于 ``now`` 所在 ISO 周周一的本地时区 00:00:00，且
  ``start <= end == now``。

时区语义：与 :mod:`weekly_summary.week_window` 一致，使用 naive 本地 ``datetime``
（不携带 tzinfo），由系统本地时间隐式表达本地时区。

``now`` 的生成范围约 1900–2100，覆盖一年中各周（含跨年周边界），充分检验
「回退到本周一并归零到 00:00:00」的不变式。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import hypothesis.strategies as st
from hypothesis import given, settings

from weekly_summary.week_window import current_week_window

# 年份范围约 1900–2100（naive 本地 datetime）。
_MIN_YEAR = 1900
_MAX_YEAR = 2100

_now_datetimes = st.datetimes(
    min_value=datetime(_MIN_YEAR, 1, 1, 0, 0, 0),
    max_value=datetime(_MAX_YEAR, 12, 31, 23, 59, 59),
)


@settings(max_examples=100)
@given(now=_now_datetimes)
def test_property_7_default_week_window(now: datetime) -> None:
    # Feature: weekly-dev-report, Property 7: 默认 Week_Window 计算
    """**Validates: Requirements 4.1**

    ``current_week_window(now).start`` 应为 ``now`` 所在 ISO 周周一的本地
    00:00:00，``end`` 应等于 ``now``，且 ``start <= end``。
    """
    window = current_week_window(now)

    # start 落在周一（weekday()==0）的 00:00:00。
    assert window.start.weekday() == 0
    assert window.start.time() == time(0, 0, 0)
    # start 的日期恰为 now 回退到本周一（ISO 周周一）。
    assert window.start.date() == now.date() - timedelta(days=now.weekday())
    # end 等于 now；start <= end。
    assert window.end == now
    assert window.start <= window.end
