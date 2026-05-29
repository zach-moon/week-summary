"""Markdown_Renderer 渲染包含性属性测试（Task 8.2 / Property 12）。

实现 :func:`weekly_summary.render.render_markdown` 的一条 Correctness Property：

- **Property 12**（Req 6.1–6.5）：对任意 :class:`AggregatedReport`，``render_markdown``
  产出的文本应包含：标题中的 ``report_identifier`` 与起止日期（``YYYY-MM-DD``）；
  「时间分布」章节中每个项目的会话数与 commit 数；「本周做了什么（commit）」章节中
  每条提交的日期与 subject；「我提了什么关键问题（codex）」章节；以及「数字」章节中
  的三类总数（commit 总数、Codex 会话总数、User_Prompt 总数）。

（Property 13「LLM 建议章节的条件渲染」按「每个属性一个文件」的约定在
``test_render_props.py`` 中独立实现，对应 Task 8.3。）

为使「子串包含」断言稳健，所有进入渲染文本的字段字符串（``report_identifier``、
commit ``subject``、``user_prompts`` 等）均取自**纯 ASCII、不含换行**的安全字符集，
从而保证它们在 Markdown 中逐字出现、不与中文章节标记冲突。``week_start`` /
``week_end`` 用 :class:`datetime.date` 生成（其 ``isoformat()`` 即 ``YYYY-MM-DD``）。
生成器允许空 ``distribution`` / ``repo_commits`` / ``repo_sessions``，并以显式
``@example`` 覆盖全空报告与带 LLM 建议的报告。

为避免 ``@given`` 与 pytest 函数级 fixture 同用触发 Hypothesis 的
``function_scoped_fixture`` 健康检查，本文件不使用任何函数级 fixture，全部输入由策略
直接生成。
"""

from __future__ import annotations

import os
from datetime import date

import hypothesis.strategies as st
from hypothesis import example, given

from weekly_summary.models import (
    AggregatedReport,
    CodexSession,
    Commit,
    ProjectDistribution,
    RepoCommits,
)
from weekly_summary.render import render_markdown

# 各固定章节标题（与 render.py / Req 6 保持一致）。
_SECTION_DISTRIBUTION = "## 时间分布（按项目目录聚合）"
_SECTION_COMMITS = "## 本周做了什么（commit）"
_SECTION_CODEX = "## 我提了什么关键问题（codex）"
_SECTION_NUMBERS = "## 数字"

# 纯 ASCII、无换行的安全字符集：逐字出现，不与中文章节标记冲突。
_SAFE_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789 _-.:/"
)
_safe_text = st.text(alphabet=_SAFE_ALPHABET, max_size=24)
# 路径段非空，使 basename（项目展示名）非空。
_seg = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=1, max_size=6)
_abs_path = st.builds(
    lambda segs: "/" + "/".join(segs), st.lists(_seg, min_size=1, max_size=3)
)
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))
_count = st.integers(min_value=0, max_value=999)


def _display_name(project_dir: str) -> str:
    """复刻 render._project_display_name 的 basename 取法（生成的路径均非保留桶）。"""
    return os.path.basename(project_dir.rstrip("/\\")) or project_dir


@st.composite
def _report(draw: st.DrawFn) -> AggregatedReport:
    """生成一份字段安全、各集合可空的 :class:`AggregatedReport`。"""
    distribution = [
        ProjectDistribution(
            project_dir=draw(_abs_path),
            commit_count=draw(_count),
            session_count=draw(_count),
        )
        for _ in range(draw(st.integers(min_value=0, max_value=4)))
    ]

    repo_commits: list[RepoCommits] = []
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        repo_id = draw(_safe_text)
        commits = [
            Commit(repo_id=repo_id, date=draw(_dates), subject=draw(_safe_text))
            for _ in range(draw(st.integers(min_value=0, max_value=3)))
        ]
        repo_commits.append(
            RepoCommits(repo_id=repo_id, repo_path=draw(_abs_path), commits=commits)
        )

    repo_sessions: list[CodexSession] = []
    for i in range(draw(st.integers(min_value=0, max_value=3))):
        prompts = draw(st.lists(_safe_text, max_size=3))
        repo_sessions.append(
            CodexSession(
                session_id=f"sess-{i}",
                project_dir=draw(_abs_path),
                date=draw(_dates),
                user_prompts=prompts,
                prompt_count=len(prompts),
            )
        )

    llm_suggestions = draw(st.one_of(st.none(), _safe_text))

    return AggregatedReport(
        report_identifier=draw(_safe_text),
        week_start=draw(_dates),
        week_end=draw(_dates),
        distribution=distribution,
        repo_commits=repo_commits,
        repo_sessions=repo_sessions,
        total_commits=draw(_count),
        total_sessions=draw(_count),
        total_user_prompts=draw(_count),
        llm_suggestions=llm_suggestions,
    )


def _empty_report(llm_suggestions: str | None = None) -> AggregatedReport:
    """全空报告（空 distribution/commits/sessions），用作显式 example。"""
    return AggregatedReport(
        report_identifier="2026-W01",
        week_start=date(2025, 12, 29),
        week_end=date(2026, 1, 4),
        distribution=[],
        repo_commits=[],
        repo_sessions=[],
        total_commits=0,
        total_sessions=0,
        total_user_prompts=0,
        llm_suggestions=llm_suggestions,
    )


# --------------------------------------------------------------------------- #
# Property 12
# --------------------------------------------------------------------------- #
@given(report=_report())
@example(report=_empty_report())
@example(report=_empty_report(llm_suggestions="x"))
def test_property_12_markdown_inclusiveness(report: AggregatedReport) -> None:
    # Feature: weekly-dev-report, Property 12: Markdown 渲染包含性
    """**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

    渲染文本应包含：标题中的 ``report_identifier`` 与起止日期；每个项目的会话数与
    commit 数；每条提交的日期与 subject；codex 章节；以及三类总数。
    """
    md = render_markdown(report)

    # —— 标题：report_identifier 与起止日期（YYYY-MM-DD）（Req 6.1）。
    title_line = md.splitlines()[0]
    assert report.report_identifier in title_line
    assert report.week_start.isoformat() in title_line
    assert report.week_end.isoformat() in title_line

    # —— 时间分布：每个项目的会话数与 commit 数（Req 6.2）。
    assert _SECTION_DISTRIBUTION in md
    for item in report.distribution:
        count_fragment = (
            f"Codex 会话 {item.session_count} 次，commit {item.commit_count} 个"
        )
        assert count_fragment in md
        assert _display_name(item.project_dir) in md

    # —— commit 章节：每条提交的日期与 subject（Req 6.3）。
    assert _SECTION_COMMITS in md
    for repo in report.repo_commits:
        for commit in repo.commits:
            assert f"{commit.date.isoformat()} {commit.subject}" in md

    # —— codex 章节存在（Req 6.4）。
    assert _SECTION_CODEX in md

    # —— 数字章节：三类总数（Req 6.5）。
    assert _SECTION_NUMBERS in md
    assert f"commit 总数：{report.total_commits}" in md
    assert f"Codex 会话总数：{report.total_sessions}" in md
    assert f"User_Prompt 总数：{report.total_user_prompts}" in md
