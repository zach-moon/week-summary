"""Markdown_Renderer 单元测试（Task 8.1）。

验证 ``render.py`` 的 :func:`render_markdown` 行为（Req 6.1–6.7）：

- 标题含 Report_Identifier 与起止日期（``YYYY-MM-DD``）。
- 四个固定章节（时间分布 / commit / 关键问题 / 数字）始终生成。
- 「自动建议（可选，LLM）」章节仅当 ``llm_suggestions is not None`` 时渲染。
- 空 distribution / commits / sessions 时优雅降级（占位行），不抛异常。
"""

from __future__ import annotations

from datetime import date

from weekly_summary.aggregate import UNMATCHED_PROJECT
from weekly_summary.models import (
    AggregatedReport,
    CodexSession,
    Commit,
    ProjectDistribution,
    RepoCommits,
)
from weekly_summary.render import render_markdown

# 各章节固定标题（与 render.py / Req 6 保持一致）。
_TITLE_PREFIX = "# 开发周报"
_SECTION_DISTRIBUTION = "## 时间分布（按项目目录聚合）"
_SECTION_COMMITS = "## 本周做了什么（commit）"
_SECTION_CODEX = "## 我提了什么关键问题（codex）"
_SECTION_NUMBERS = "## 数字"
_SECTION_LLM = "## 自动建议（可选，LLM）"


def _full_report(llm_suggestions: str | None = None) -> AggregatedReport:
    """构造一份含 commit / session / 分布的完整报告，便于复用。"""
    return AggregatedReport(
        report_identifier="2026-W22",
        week_start=date(2026, 5, 25),
        week_end=date(2026, 5, 29),
        distribution=[
            ProjectDistribution(project_dir="/home/v/proj-a", commit_count=3, session_count=2),
            ProjectDistribution(project_dir="/home/v/proj-b", commit_count=0, session_count=0),
        ],
        repo_commits=[
            RepoCommits(
                repo_id="proj-a",
                repo_path="/home/v/proj-a",
                commits=[
                    Commit(repo_id="proj-a", date=date(2026, 5, 26), subject="修复登录 bug"),
                    Commit(repo_id="proj-a", date=date(2026, 5, 27), subject="add tests"),
                ],
            ),
            RepoCommits(repo_id="proj-b", repo_path="/home/v/proj-b", commits=[]),
        ],
        repo_sessions=[
            CodexSession(
                session_id="uuid-1",
                project_dir="/home/v/proj-a",
                date=date(2026, 5, 26),
                user_prompts=["如何保护 App Router 路由？", "怎么做 oauth 回调？"],
                prompt_count=2,
            ),
        ],
        total_commits=3,
        total_sessions=2,
        total_user_prompts=5,
        llm_suggestions=llm_suggestions,
    )


def _empty_report(llm_suggestions: str | None = None) -> AggregatedReport:
    """构造一份完全无活动的报告（空 distribution/commits/sessions）。"""
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


def test_title_contains_identifier_and_dates() -> None:
    """标题含 Report_Identifier 与起止日期（YYYY-MM-DD）（Req 6.1）。"""
    md = render_markdown(_full_report())
    first_line = md.splitlines()[0]
    assert first_line.startswith(_TITLE_PREFIX)
    assert "2026-W22" in first_line
    assert "2026-05-25" in first_line
    assert "2026-05-29" in first_line


def test_all_fixed_sections_present() -> None:
    """四个固定章节始终生成（Req 6.2–6.5）。"""
    md = render_markdown(_full_report())
    assert _SECTION_DISTRIBUTION in md
    assert _SECTION_COMMITS in md
    assert _SECTION_CODEX in md
    assert _SECTION_NUMBERS in md


def test_distribution_lists_counts_per_project() -> None:
    """时间分布逐项列出会话数与 commit 数（Req 6.2）。"""
    md = render_markdown(_full_report())
    assert "proj-a" in md
    assert "Codex 会话 2 次" in md
    assert "commit 3 个" in md
    # 零活动项目也应出现（聚合层负责包含，渲染层应忠实呈现）。
    assert "proj-b" in md


def test_commits_grouped_with_date_and_subject() -> None:
    """commit 章节按仓库分组，列带日期的 subject（Req 6.3）。"""
    md = render_markdown(_full_report())
    assert "### proj-a" in md
    assert "2026-05-26" in md
    assert "修复登录 bug" in md
    assert "2026-05-27" in md
    assert "add tests" in md


def test_codex_lists_user_prompts() -> None:
    """关键问题章节按项目分组，列出真实 User_Prompt（Req 6.4）。"""
    md = render_markdown(_full_report())
    assert "如何保护 App Router 路由？" in md
    assert "怎么做 oauth 回调？" in md


def test_numbers_section_totals() -> None:
    """数字章节列出三类总数（Req 6.5）。"""
    md = render_markdown(_full_report())
    assert "commit 总数：3" in md
    assert "Codex 会话总数：2" in md
    assert "User_Prompt 总数：5" in md


def test_llm_section_omitted_when_none() -> None:
    """llm_suggestions 为 None 时省略 LLM 章节，其余章节正常生成（Req 6.7）。"""
    md = render_markdown(_full_report(llm_suggestions=None))
    assert _SECTION_LLM not in md
    # 其余固定章节仍在。
    assert _SECTION_DISTRIBUTION in md
    assert _SECTION_NUMBERS in md


def test_llm_section_rendered_when_present() -> None:
    """llm_suggestions 非 None 时渲染 LLM 章节并含建议内容（Req 6.6）。"""
    md = render_markdown(_full_report(llm_suggestions="下周建议：继续打磨认证流程。"))
    assert _SECTION_LLM in md
    assert "下周建议：继续打磨认证流程。" in md


def test_llm_section_rendered_for_empty_string() -> None:
    """空字符串与 None 不同：空字符串属于「非 None」，应渲染章节（Req 6.6）。"""
    md = render_markdown(_full_report(llm_suggestions=""))
    assert _SECTION_LLM in md


def test_empty_report_renders_placeholders_without_crash() -> None:
    """空 distribution/commits/sessions 时优雅降级（占位行），不抛异常（Req 6.7）。"""
    md = render_markdown(_empty_report())
    # 所有固定章节仍生成。
    assert _SECTION_DISTRIBUTION in md
    assert _SECTION_COMMITS in md
    assert _SECTION_CODEX in md
    assert _SECTION_NUMBERS in md
    # 占位提示出现，且总数为零。
    assert "（本周暂无项目活动）" in md
    assert "（本周无提交记录）" in md
    assert "（本周无 Codex 会话）" in md
    assert "commit 总数：0" in md
    # 无 LLM 章节。
    assert _SECTION_LLM not in md


def test_unmatched_bucket_displayed_as_unclassified() -> None:
    """保留桶 __unmatched__ 展示为「未归类」（与聚合层契约一致）。"""
    report = AggregatedReport(
        report_identifier="2026-W22",
        week_start=date(2026, 5, 25),
        week_end=date(2026, 5, 29),
        distribution=[
            ProjectDistribution(project_dir=UNMATCHED_PROJECT, commit_count=1, session_count=1),
        ],
        repo_commits=[],
        repo_sessions=[],
        total_commits=1,
        total_sessions=1,
        total_user_prompts=0,
    )
    md = render_markdown(report)
    assert "未归类" in md
    assert UNMATCHED_PROJECT not in md


def test_render_returns_str_ending_with_newline() -> None:
    """渲染保持纯函数：返回字符串、不做文件 IO，以换行收尾。"""
    md = render_markdown(_full_report())
    assert isinstance(md, str)
    assert md.endswith("\n")
