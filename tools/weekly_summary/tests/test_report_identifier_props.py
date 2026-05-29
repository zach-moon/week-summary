"""Report_Identifier 属性测试（Task 3.4 / Property 9）。

实现 Week_Window 组件中 :func:`weekly_summary.week_window.report_identifier`
的 Correctness Property：

- **Property 9**（Req 4.3）：对任意日期 ``d``，``report_identifier(d)`` 应形如
  ``YYYY-Www``（周序号两位补零），且其 ISO 年 / ISO 周等于 ``d.isocalendar()``
  的结果，从而正确处理跨年周（ISO 年可能 != 日历年）。

ISO 8601 注意事项：``date.isocalendar()`` 返回的 *ISO 年* 在年初 / 年末可能与
日历年不同（例如 1 月初的日期可能属于上一年的最后一周、12 月末的日期可能属于
下一年的第 1 周）。下面的 ``@example`` 显式覆盖这些跨年周边界。
"""

from __future__ import annotations

from datetime import date

import hypothesis.strategies as st
from hypothesis import example, given

from weekly_summary.week_window import report_identifier

# 年份范围约 1900–2100（naive 本地 date）。
_MIN_YEAR = 1900
_MAX_YEAR = 2100

_dates = st.dates(min_value=date(_MIN_YEAR, 1, 1), max_value=date(_MAX_YEAR, 12, 31))


@given(d=_dates)
# 跨年周边界示例：2021-01-01 属于 ISO 2020-W53；2019-12-30 属于 ISO 2020-W01。
@example(d=date(2021, 1, 1))
@example(d=date(2019, 12, 30))
@example(d=date(2020, 12, 31))
def test_property_9_report_identifier_iso(d: date) -> None:
    # Feature: weekly-dev-report, Property 9: Report_Identifier 的 ISO 计算
    """**Validates: Requirements 4.3**

    ``report_identifier(d)`` 应等于按 ``d.isocalendar()`` 的 ISO 年与 ISO 周序号
    （两位补零）拼出的 ``YYYY-Www``，正确处理跨年周（ISO 年可能 != 日历年）。
    """
    iso = d.isocalendar()
    expected = f"{iso.year}-W{iso.week:02d}"

    result = report_identifier(d)

    # ISO 年 / 周与 isocalendar() 一致。
    assert result == expected
    # 形如 YYYY-Www：周序号始终两位补零。
    assert result[-3] == "W"
    assert len(result.split("-W")[1]) == 2
