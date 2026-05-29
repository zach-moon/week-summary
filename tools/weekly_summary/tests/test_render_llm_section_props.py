"""Markdown_Renderer 属性测试（Task 8.3 / Property 13）。

实现 :func:`weekly_summary.render.render_markdown` 的 Property 13：

- **Property 13**（Req 6.6、6.7）：对任意 :class:`AggregatedReport`，渲染文本包含
  「自动建议（可选，LLM）」章节，当且仅当 ``report.llm_suggestions is not None``；
  无论该章节是否存在，其余四个固定章节（时间分布 / commit / codex / 数字）都应正常
  生成。

为使「子串包含」断言稳健，所有进入渲染文本的字段字符串（``report_identifier``、
commit ``subject``、``user_prompts``、``llm_suggestions`` 等）均取自**纯 ASCII、不含
换行**的安全字符集，从而保证它们逐字出现、不与中文章节标记冲突。生成器同时覆盖
``llm_suggestions`` 为 ``None`` 与非 ``None``（含空串与非空串）三类情形，并以显式
``@example`` 固定这三种边界。
"""

from __future__ import annotations

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
_SECTION_LLM = "## 自动建议（可选，LLM）"

# 纯 ASCII、无换行的安全字符集：逐字出现，不与中文章节标记冲突。
_SAFE_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789 _-.:/"
)
_safe_text = st.text(alphabet=_SAFE_ALPHABET, max_size=24)
# 路径段非空，使 basename（项目展示名）非空。
_seg = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=1, max_size=6)
_abs_path = st.builds(lambda segs: "/" + "/".join(segs), st.lists(_seg, min_size=1, max_size=3))
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))
_count = st.integers(min_value=0, max_value=999)

# llm_suggestions 同时覆盖 None / 空串 / 非空串（None vs non-None 是本属性的关键划分）。
_llm_suggestions = st.one_of(st.none(), _safe_text)


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
        llm_suggestions=draw(_llm_suggestions),
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
# Property 13
# --------------------------------------------------------------------------- #
@given(report=_report())
@example(report=_empty_report(llm_suggestions=None))
@example(report=_empty_report(llm_suggestions=""))
@example(report=_empty_report(llm_suggestions="下周建议：拆分大函数"))
def test_property_13_llm_section_conditional(report: AggregatedReport) -> None:
    # Feature: weekly-dev-report, Property 13: LLM 建议章节的条件渲染
    """**Validates: Requirements 6.6, 6.7**

    「自动建议（可选，LLM）」章节出现当且仅当 ``llm_suggestions is not None``（Req 6.6）；
    无论该章节是否存在，其余四个固定章节都应正常生成（Req 6.7）。
    """
    md = render_markdown(report)

    # —— 条件章节：出现 iff llm_suggestions 非 None（Req 6.6）。
    assert (_SECTION_LLM in md) == (report.llm_suggestions is not None)

    # —— 其余固定章节始终生成（Req 6.7）。
    assert _SECTION_DISTRIBUTION in md
    assert _SECTION_COMMITS in md
    assert _SECTION_CODEX in md
    assert _SECTION_NUMBERS in md
