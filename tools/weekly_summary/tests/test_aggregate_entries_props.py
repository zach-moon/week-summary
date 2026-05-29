"""Report_Aggregator 建条目与计数属性测试（Task 7.2 / Property 10）。

实现 :mod:`weekly_summary.aggregate` 的一条 Correctness Property：

- **Property 10**（Req 5.1、5.2）：``aggregate`` 产出的 ``distribution`` 为配置中
  **每个**项目目录恰好建一条条目（含 commit / session 均为零的项目），且每条条目的
  ``commit_count`` / ``session_count`` 等于输入中归属该项目的实际数量；未匹配任何配置
  项目的活动归入保留桶 :data:`~weekly_summary.aggregate.UNMATCHED_PROJECT`，且该桶仅在
  确有未归类活动时出现。

（Property 11「聚合排序不变式」按「每个属性一个文件」的约定在
``test_aggregate_props.py`` 中独立实现。）

为独立验证「最长前缀归属 + 保留桶」逻辑（避免与实现耦合成同义反复），本文件按
design.md「Report_Aggregator」一节描述的归属规则，**独立重实现**一份期望计数算法
（:func:`_expected_counts`），再与 ``aggregate`` 的输出比对。

输入空间：配置项目目录用以 ``/`` 开头、单段取自小字母表的绝对路径生成（绝不产生
``"."`` / ``".."`` / ``"~"``，使 ``os.path.normpath`` 等同恒等映射、归一化可预测）；
commit / session 的归属目标路径随机取「恰为某配置项目」「位于某配置项目子树下（exercise
最长前缀）」或「全新随机路径（多半未匹配）」三类，覆盖命中、嵌套命中与未归类三种情形。

为避免 ``@given`` 与 pytest 函数级 fixture（如 ``tmp_path``）同用触发 Hypothesis
的 ``function_scoped_fixture`` 健康检查，本文件不使用任何函数级 fixture，全部输入由
策略直接生成。
"""

from __future__ import annotations

import os
from datetime import date, datetime, time

import hypothesis.strategies as st
from hypothesis import given

from weekly_summary.aggregate import UNMATCHED_PROJECT, aggregate
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
# 路径段取自小字母表，绝不产生 "." / ".." / "~"，使 os.path.normpath 等同于恒等映射，
# 归一化行为对测试可预测。
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


# --------------------------------------------------------------------------- #
# 独立重实现 design 中的「归一化 + 最长前缀匹配」归属规则
# --------------------------------------------------------------------------- #
def _normalize(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path))


def _is_within(child: str, parent: str) -> bool:
    if child == parent:
        return True
    parent_with_sep = parent if parent.endswith(os.sep) else parent + os.sep
    return child.startswith(parent_with_sep)


def _dedup_projects(repos: list[str]) -> list[tuple[str, str]]:
    """按归一化路径去重（保留首个原始字符串），返回 ``[(归一化, 原始)]``。"""
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for repo in repos:
        normalized = _normalize(repo)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append((normalized, repo))
    return result


def _match(target: str, normalized_projects: list[tuple[str, str]]) -> str | None:
    """最长前缀匹配，返回命中项目的原始字符串；无命中返回 ``None``。"""
    normalized_target = _normalize(target)
    best: str | None = None
    best_len = -1
    for normalized_path, original in normalized_projects:
        if _is_within(normalized_target, normalized_path) and len(normalized_path) > best_len:
            best = original
            best_len = len(normalized_path)
    return best


def _expected_counts(
    config: Config,
    repo_commits: list[RepoCommits],
    sessions: list[CodexSession],
) -> tuple[list[str], dict[str, int], dict[str, int], int, int]:
    """独立计算每个配置项目的期望 commit/session 计数与未归类计数。

    Returns:
        ``(project_order, commit_counts, session_counts, unmatched_commits, unmatched_sessions)``
    """
    dedup = _dedup_projects(config.repos)
    project_order = [original for _, original in dedup]
    commit_counts = {original: 0 for original in project_order}
    session_counts = {original: 0 for original in project_order}

    unmatched_commits = 0
    for rc in repo_commits:
        count = len(rc.commits)
        if count == 0:
            continue
        matched = _match(rc.repo_path, dedup)
        if matched is not None:
            commit_counts[matched] += count
        else:
            unmatched_commits += count

    unmatched_sessions = 0
    for session in sessions:
        matched = _match(session.project_dir, dedup)
        if matched is not None:
            session_counts[matched] += 1
        else:
            unmatched_sessions += 1

    return project_order, commit_counts, session_counts, unmatched_commits, unmatched_sessions


def _window() -> WeekWindow:
    """构造一个固定时间窗（聚合仅用其 identifier 与起止日期，与归属无关）。"""
    return WeekWindow(
        start=datetime.combine(date(2026, 5, 25), time(0, 0, 0)),
        end=datetime.combine(date(2026, 5, 31), time(23, 59, 59)),
        report_identifier="2026-W22",
    )


# --------------------------------------------------------------------------- #
# Property 10
# --------------------------------------------------------------------------- #
@given(case=_aggregate_case())
def test_property_10_distribution_entry_per_project_and_counts(
    case: tuple[Config, list[RepoCommits], list[CodexSession]],
) -> None:
    # Feature: weekly-dev-report, Property 10: 聚合为每个项目建条目且计数正确
    """**Validates: Requirements 5.1, 5.2**

    ``aggregate`` 的 ``distribution`` 为每个配置项目恰好建一条条目（含零活动项目），
    其 ``commit_count`` / ``session_count`` 等于独立计算的归属计数；未归类活动归入
    ``__unmatched__`` 桶，且该桶仅在确有未归类活动时出现。
    """
    config, repo_commits, sessions = case
    (
        project_order,
        commit_counts,
        session_counts,
        unmatched_commits,
        unmatched_sessions,
    ) = _expected_counts(config, repo_commits, sessions)

    report = aggregate(config, _window(), repo_commits, sessions)
    distribution = report.distribution

    configured_entries = [d for d in distribution if d.project_dir != UNMATCHED_PROJECT]
    configured_map = {d.project_dir: d for d in configured_entries}

    # 每个配置项目恰好一条条目（无重复键 → map 大小等于条目数）。
    assert len(configured_map) == len(configured_entries)
    # distribution 的项目集合恰等于配置项目集合（含零活动项目）。
    assert set(configured_map) == set(project_order)
    assert len(configured_entries) == len(project_order)

    # 每条条目的计数等于独立计算的归属数量（含零活动项目）。
    for project in project_order:
        entry = configured_map[project]
        assert entry.commit_count == commit_counts[project]
        assert entry.session_count == session_counts[project]

    # 保留桶：仅在确有未归类活动时出现，且计数正确。
    unmatched_entries = [d for d in distribution if d.project_dir == UNMATCHED_PROJECT]
    if unmatched_commits > 0 or unmatched_sessions > 0:
        assert len(unmatched_entries) == 1
        assert unmatched_entries[0].commit_count == unmatched_commits
        assert unmatched_entries[0].session_count == unmatched_sessions
    else:
        assert unmatched_entries == []
