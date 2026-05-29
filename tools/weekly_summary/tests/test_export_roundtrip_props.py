"""Data_Exporter 属性测试（Task 9.2 / Property 17）。

实现 :mod:`weekly_summary.export` 的 round-trip Correctness Property：

- **Property 17**（Req 10.3、10.4）：对任意合法 :class:`AggregatedReport`，规范的
  round-trip 等价定义在 **JSON 投影（projection）层面**——即

      to_dict(from_dict(to_dict(report))) == to_dict(report)

  这与 ``export.py`` 模块文档一致：由于隐私边界，``repo_codex`` 只保留摘要
  （``themes`` / ``key_questions`` / ``session_count``），``from_dict`` 重建出的
  ``repo_sessions`` 是与该投影一致的摘要重建而非原始会话，故规范形式取「导出后的
  JSON 字典」。所有其它契约字段（identifier、起止日期、distribution、repo_commits、
  numbers、llm_suggestions）在该投影下被完整保留。

输入空间覆盖：空 ``distribution`` / ``repo_commits`` / ``repo_sessions``；
``llm_suggestions`` 取 ``None`` 或字符串；多个会话共享同一 ``project_dir``（exercise
``repo_codex`` 分组）以及互不相同的 ``project_dir``。
"""

from __future__ import annotations

from datetime import date

import hypothesis.strategies as st
from hypothesis import example, given

from weekly_summary.export import from_dict, to_dict
from weekly_summary.models import (
    AggregatedReport,
    CodexSession,
    Commit,
    ProjectDistribution,
    RepoCommits,
)

# round-trip 在字典层面比较，故字符串可含任意 Unicode（不经 JSON 文本序列化）。
_text = st.text(max_size=24)
_dates = st.dates(min_value=date(1, 1, 1), max_value=date(9999, 12, 31))
_count = st.integers(min_value=0, max_value=10_000)

# 共享的小项目目录池：制造 project_dir 碰撞以充分 exercise repo_codex 分组重建。
_project_pool = st.sampled_from(
    ["/p/a", "/p/b", "/p/c", "/users/me/proj-x", "/users/me/proj-y"]
)


@st.composite
def _report(draw: st.DrawFn) -> AggregatedReport:
    """生成一份结构合法、各集合可空的 :class:`AggregatedReport`。"""
    distribution = [
        ProjectDistribution(
            project_dir=draw(_project_pool),
            commit_count=draw(_count),
            session_count=draw(_count),
        )
        for _ in range(draw(st.integers(min_value=0, max_value=4)))
    ]

    repo_commits: list[RepoCommits] = []
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        repo_id = draw(_text)
        commits = [
            Commit(repo_id=repo_id, date=draw(_dates), subject=draw(_text))
            for _ in range(draw(st.integers(min_value=0, max_value=3)))
        ]
        repo_commits.append(
            RepoCommits(repo_id=repo_id, repo_path=draw(_text), commits=commits)
        )

    repo_sessions: list[CodexSession] = []
    for i in range(draw(st.integers(min_value=0, max_value=5))):
        prompts = draw(st.lists(_text, max_size=3))
        repo_sessions.append(
            CodexSession(
                session_id=f"sess-{i}",
                project_dir=draw(_project_pool),
                date=draw(_dates),
                user_prompts=prompts,
                prompt_count=len(prompts),
            )
        )

    return AggregatedReport(
        report_identifier=draw(_text),
        week_start=draw(_dates),
        week_end=draw(_dates),
        distribution=distribution,
        repo_commits=repo_commits,
        repo_sessions=repo_sessions,
        total_commits=draw(_count),
        total_sessions=draw(_count),
        total_user_prompts=draw(_count),
        llm_suggestions=draw(st.one_of(st.none(), _text)),
    )


def _empty_report(llm_suggestions: str | None) -> AggregatedReport:
    return AggregatedReport(
        report_identifier="2026-W22",
        week_start=date(2026, 5, 25),
        week_end=date(2026, 5, 31),
        distribution=[],
        repo_commits=[],
        repo_sessions=[],
        total_commits=0,
        total_sessions=0,
        total_user_prompts=0,
        llm_suggestions=llm_suggestions,
    )


@given(report=_report())
@example(report=_empty_report(None))
@example(report=_empty_report(""))
@example(report=_empty_report("下周建议：继续推进认证流程。"))
def test_property_17_json_roundtrip_projection_equivalence(
    report: AggregatedReport,
) -> None:
    # Feature: weekly-dev-report, Property 17: JSON 序列化 round-trip 等价
    """**Validates: Requirements 10.3, 10.4**

    规范 round-trip 定义在 JSON 投影层面：
    ``to_dict(from_dict(to_dict(report))) == to_dict(report)``。
    """
    projection = to_dict(report)
    roundtrip = to_dict(from_dict(projection))

    assert roundtrip == projection
