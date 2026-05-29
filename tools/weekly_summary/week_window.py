"""Week_Window — 本周时间窗与周报标识计算（Req 4）。

本模块提供三个纯函数，对应设计文档「Components and Interfaces」中
``Week_Window`` 组件的接口签名：

- :func:`current_week_window`：默认时间窗（本周一 00:00:00 ~ now）。
- :func:`week_window_for`：指定周时间窗（周一 00:00:00 ~ 周日 23:59:59）。
- :func:`report_identifier`：依据 ISO 8601 ``isocalendar()`` 产出 ``YYYY-Www``。

时区语义：全部使用**本地时区**。与设计其余部分一致，这里采用 naive 本地
``datetime``（不携带 tzinfo），由系统本地时间隐式表达本地时区。

ISO 8601 注意事项：``date.isocalendar()`` 返回的 *ISO 年* 在年初 / 年末可能
与日历年不同（例如 1 月初的日期可能属于上一年的最后一周，12 月末的日期可能
属于下一年的第 1 周）。本模块始终以 ``isocalendar()`` 的结果为准，从而正确
处理跨年周（Req 4.3）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .models import WeekWindow

__all__ = [
    "current_week_window",
    "week_window_for",
    "report_identifier",
]


def report_identifier(d: date) -> str:
    """依据 ISO 8601 计算周报标识 ``<ISO-year>-W<week>``（Req 4.3）。

    使用 :meth:`datetime.date.isocalendar` 取得 ISO 年与 ISO 周序号，周序号
    两位补零。ISO 年可能与日历年不同（跨年周），此处以 ISO 年为准。

    Args:
        d: 任意日期（通常取 Week_Window 的起始日期，即本周一）。

    Returns:
        形如 ``"2026-W22"`` 的周报标识。
    """
    iso = d.isocalendar()
    # Python 3.9+ 下 isocalendar() 返回具名元组（.year/.week/.weekday）。
    return f"{iso.year}-W{iso.week:02d}"


def current_week_window(now: datetime | None = None) -> WeekWindow:
    """计算默认时间窗：本周一 00:00:00（本地时区）至 ``now``（Req 4.1）。

    Args:
        now: 当前时刻；为 ``None`` 时取本地当前时间 :func:`datetime.now`。

    Returns:
        ``start`` 为 ``now`` 所在周周一的本地 00:00:00，``end == now``，且
        ``report_identifier`` 依据 ``start`` 的日期按 ISO 8601 计算。
    """
    if now is None:
        now = datetime.now()

    # weekday(): 周一为 0、周日为 6。回退到本周一并归零到 00:00:00。
    monday_date = now.date() - timedelta(days=now.weekday())
    start = datetime.combine(monday_date, time(0, 0, 0))

    return WeekWindow(
        start=start,
        end=now,
        report_identifier=report_identifier(start.date()),
    )


def week_window_for(year: int, iso_week: int) -> WeekWindow:
    """计算指定 ISO 周的时间窗（Req 4.2）。

    时间窗为该周周一 00:00:00 至周日 23:59:59（本地时区）。

    Args:
        year: ISO 8601 周所属的年份（ISO 年）。
        iso_week: ISO 8601 周序号（1 ~ 52/53）。

    Returns:
        ``start`` 为该周周一 00:00:00、``end`` 为该周周日 23:59:59 的
        :class:`~weekly_summary.models.WeekWindow`，``report_identifier`` 为
        ``f"{year}-W{iso_week:02d}"``。
    """
    # ISO 工作日：1 = 周一、7 = 周日。
    monday_date = date.fromisocalendar(year, iso_week, 1)
    sunday_date = date.fromisocalendar(year, iso_week, 7)

    start = datetime.combine(monday_date, time(0, 0, 0))
    end = datetime.combine(sunday_date, time(23, 59, 59))

    return WeekWindow(
        start=start,
        end=end,
        report_identifier=report_identifier(monday_date),
    )
