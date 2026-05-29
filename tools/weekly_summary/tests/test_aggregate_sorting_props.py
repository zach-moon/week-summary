"""Report_Aggregator 排序不变式属性测试（Task 7.3 / Property 11）。

实现 :mod:`weekly_summary.aggregate` 的 Correctness Property 11（Req 5.3）：

- **Property 11**：*For any* 一组项目分布，``aggregate`` 返回的 ``distribution``
  应按 ``(commit_count, session_count)`` 降序排列（任意相邻条目满足非升序）。

遵循「每条属性独立一个测试文件」的约定（见 tasks.md 约定）：本文件只实现 Property 11，
并自带其所需的生成器与时间窗构造，不依赖其它属性测试文件。

输入空间：配置项目目录用以 ``/`` 开头、单段取自小字母表的绝对路径生成（绝不产生
``.`` / ``..`` / ``~``，使 ``os.path.normpath`` 等同于恒等映射，归属行为可预测）；
commit / session 的归属目标路径随机取「恰为某配置项目」「位于某配置项目子树下」或
「全新随机路径（多半未匹配）」三类，覆盖命中、嵌套命中与未归类三种情形，从而让
``distribution`` 各条目的 ``(commit_count, session_count)`` 取值充分多样。
"""

from __future__ import annotations

from datetime import date, datetime, time

import hypothesis.strategies as st
from hypothesis import given

from weekly_summary.aggregate import aggregate
from weekly_summary.models import (
    CodexSession,
    Commit,
    Config,
    RepoCommits,
    WeekWindow,
)

# --------------------------------------------------------------------------- #
# 生成器：绝对路径、目标路径、commit / session 集合
# --------------------------------------------------------------------------- #
# 路径段取自小字母表，绝不产生 "." / ".." / "~"，使 os.path.normpath 等同于恒等映射。
_SEG = st.text(alphabet="abcde", min_size=1, max_size=3)
_abs_path = st.builds(
    lambda segs: "/" + "/".join(segs),
    st.lists(_SEG, min_size=1, max_size=3),
)

# commit subject / session prompt 用安全短文本（不影响归属，仅充实输入）。
_safe_text = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _-", max_size=12)
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


def _target_path(repos: list[str]) -> st.SearchStrategy[str]:
    """构造「归属目标路径」策略：命中 / 嵌套命中 / 未归类三类混合。"""
    if not repos:
        return _abs_path
    exact = st.sampled_from(repos)
    child = st.builds(
        lambda base, extra: base.rstrip("/") + "/" + "/".join(extra),
        st.sampled_from(repos),
        st.lists(_SEG, min_size=1, max_size=2),
    )
    return st.one_of(_abs_path, exact, child)


@st.composite
def _aggregate_case(
    draw: st.DrawFn,
) -> tuple[Config, list[RepoCommits], list[CodexSession]]:
    """生成一组 ``(config, repo_commits, sessions)`` 聚合输入。"""
    repos = draw(st.lists(_abs_path, min_size=0, max_size=4, unique=True))
    target = _target_path(repos)

    # repo_commits：每组一个目标路径 + 0~3 条 commit（空组用于验证不产生未归类）。
    repo_commits: list[RepoCommits] = []
    for _ in range(draw(st.integers(min_value=0, max_value=4))):
        repo_path = draw(target)
        repo_id = draw(_safe_text)
        commits = [
            Commit(repo_id=repo_id, date=draw(_dates), subject=draw(_safe_text))
            for _ in range(draw(st.integers(min_value=0, max_value=3)))
        ]
        repo_commits.append(
            RepoCommits(repo_id=repo_id, repo_path=repo_path, commits=commits)
        )

    # sessions：每个会话一个目标路径（cwd），prompt 数任意。
    sessions: list[CodexSession] = []
    for i in range(draw(st.integers(min_value=0, max_value=5))):
        prompts = draw(st.lists(_safe_text, max_size=3))
        sessions.append(
            CodexSession(
                session_id=f"sess-{i}",
                project_dir=draw(target),
                date=draw(_dates),
                user_prompts=prompts,
                prompt_count=len(prompts),
            )
        )

    config = Config(repos=repos)
    return config, repo_commits, sessions


def _window() -> WeekWindow:
    """构造一个固定时间窗（聚合仅用其 identifier 与起止日期，与排序无关）。"""
    return WeekWindow(
        start=datetime.combine(date(2026, 5, 25), time(0, 0, 0)),
        end=datetime.combine(date(2026, 5, 31), time(23, 59, 59)),
        report_identifier="2026-W22",
    )


# --------------------------------------------------------------------------- #
# Property 11
# --------------------------------------------------------------------------- #
@given(case=_aggregate_case())
def test_property_11_distribution_sorted_descending(
    case: tuple[Config, list[RepoCommits], list[CodexSession]],
) -> None:
    # Feature: weekly-dev-report, Property 11: 聚合排序不变式
    """**Validates: Requirements 5.3**

    ``aggregate`` 的 ``distribution`` 按 ``(commit_count, session_count)`` 降序排列：
    任意相邻条目满足前者的 ``(commit_count, session_count)`` 不小于后者（非升序）。
    """
    config, repo_commits, sessions = case
    report = aggregate(config, _window(), repo_commits, sessions)
    distribution = report.distribution

    for prev, cur in zip(distribution, distribution[1:]):
        assert (prev.commit_count, prev.session_count) >= (
            cur.commit_count,
            cur.session_count,
        )
