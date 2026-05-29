"""Markdown_Renderer（``render.py``）— Req 6、7。

职责：把 :class:`~weekly_summary.models.AggregatedReport` 渲染为一份结构清晰的
**中文 Markdown** 周报文本。

设计依据：design.md「Components and Interfaces / Markdown_Renderer（`render.py`）— Req 6、7」。

固定章节（无论数据多寡始终生成）：

1. 标题 ``# 开发周报 <report_identifier>（YYYY-MM-DD ~ YYYY-MM-DD）``，含
   Report_Identifier 与 Week_Window 起止日期（Req 6.1）。
2. ``## 时间分布（按项目目录聚合）``——逐项列出每个项目的 Codex 会话数与 commit 数
   （Req 6.2）。
3. ``## 本周做了什么（commit）``——按仓库分组，列出带日期的提交标题（Req 6.3）。
4. ``## 我提了什么关键问题（codex）``——按项目分组，列出该项目下的关键问题
   （即真实 User_Prompt）（Req 6.4）。
5. ``## 数字``——commit 总数 / Codex 会话总数 / User_Prompt 总数（Req 6.5）。

条件章节：

6. ``## 自动建议（可选，LLM）``——**仅当** ``report.llm_suggestions is not None``
   时渲染（Req 6.6）；否则整段省略，但其余固定章节照常生成（Req 6.7）。

说明：
- 主题（themes）提取与 LLM 归纳属于后续任务，此处「关键问题」忠实地列出已采集到的
  真实 User_Prompt 文本，不做额外加工。
- 项目展示名取 ``project_dir`` 的 basename 以便阅读；保留桶 ``__unmatched__`` 展示为
  「未归类」。
"""

from __future__ import annotations

import os

from .aggregate import UNMATCHED_PROJECT
from .models import AggregatedReport

__all__ = ["render_markdown"]

# 各章节固定标题（与 design.md / Req 6 保持一致）。
_SECTION_DISTRIBUTION = "## 时间分布（按项目目录聚合）"
_SECTION_COMMITS = "## 本周做了什么（commit）"
_SECTION_CODEX = "## 我提了什么关键问题（codex）"
_SECTION_NUMBERS = "## 数字"
_SECTION_LLM = "## 自动建议（可选，LLM）"


def _project_display_name(project_dir: str) -> str:
    """把项目目录转换为便于阅读的展示名。

    取路径 basename；保留桶 :data:`~weekly_summary.aggregate.UNMATCHED_PROJECT`
    展示为「未归类」；basename 为空（如以分隔符结尾）时回退为原始字符串。
    """
    if project_dir == UNMATCHED_PROJECT:
        return "未归类"
    basename = os.path.basename(project_dir.rstrip("/\\"))
    return basename or project_dir


def _render_distribution(report: AggregatedReport) -> list[str]:
    """渲染「时间分布」章节：逐项列出 Codex 会话数与 commit 数（Req 6.2）。"""
    lines = [_SECTION_DISTRIBUTION, ""]
    if not report.distribution:
        lines.append("（本周暂无项目活动）")
        return lines
    for item in report.distribution:
        name = _project_display_name(item.project_dir)
        lines.append(
            f"- {name}：Codex 会话 {item.session_count} 次，commit {item.commit_count} 个"
        )
    return lines


def _render_commits(report: AggregatedReport) -> list[str]:
    """渲染「本周做了什么（commit）」章节：按仓库分组列带日期的 subject（Req 6.3）。"""
    lines = [_SECTION_COMMITS, ""]
    repos_with_commits = [rc for rc in report.repo_commits if rc.commits]
    if not repos_with_commits:
        lines.append("（本周无提交记录）")
        return lines
    for repo in repos_with_commits:
        lines.append(f"### {repo.repo_id}")
        for commit in repo.commits:
            lines.append(f"- {commit.date.isoformat()} {commit.subject}")
        lines.append("")
    # 去掉末尾多余空行（统一由组装层管理章节间距）。
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _render_codex(report: AggregatedReport) -> list[str]:
    """渲染「我提了什么关键问题（codex）」章节：按项目分组列关键问题（Req 6.4）。

    将会话按 ``project_dir`` 聚合（保持首次出现顺序），逐项目列出其下所有真实
    User_Prompt 作为「关键问题」。主题归纳留待后续 LLM 任务，此处忠实呈现已有数据。
    """
    lines = [_SECTION_CODEX, ""]
    sessions = report.repo_sessions
    if not sessions:
        lines.append("（本周无 Codex 会话）")
        return lines

    # 按 project_dir 分组，保持首次出现顺序。
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for session in sessions:
        if session.project_dir not in grouped:
            grouped[session.project_dir] = []
            order.append(session.project_dir)
        grouped[session.project_dir].extend(session.user_prompts)

    for project_dir in order:
        name = _project_display_name(project_dir)
        lines.append(f"### {name}")
        prompts = grouped[project_dir]
        if prompts:
            for prompt in prompts:
                lines.append(f"- {prompt}")
        else:
            lines.append("（本周无关键问题）")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _render_numbers(report: AggregatedReport) -> list[str]:
    """渲染「数字」章节：commit 总数 / Codex 会话总数 / User_Prompt 总数（Req 6.5）。"""
    return [
        _SECTION_NUMBERS,
        "",
        f"- commit 总数：{report.total_commits}",
        f"- Codex 会话总数：{report.total_sessions}",
        f"- User_Prompt 总数：{report.total_user_prompts}",
    ]


def render_markdown(report: AggregatedReport) -> str:
    """把聚合后的周报数据渲染为中文 Markdown 文本（Req 6）。

    Args:
        report: 聚合后的完整周报数据模型。

    Returns:
        渲染好的 Markdown 字符串。固定章节始终生成；「自动建议（可选，LLM）」章节
        仅当 ``report.llm_suggestions is not None`` 时附加（Req 6.6、6.7）。
    """
    title = (
        f"# 开发周报 {report.report_identifier}"
        f"（{report.week_start.isoformat()} ~ {report.week_end.isoformat()}）"
    )

    sections: list[list[str]] = [
        [title],
        _render_distribution(report),
        _render_commits(report),
        _render_codex(report),
        _render_numbers(report),
    ]

    # 条件章节：仅当 llm_suggestions 非 None 时渲染（Req 6.6、6.7）。
    if report.llm_suggestions is not None:
        sections.append([_SECTION_LLM, "", report.llm_suggestions])

    # 章节之间以单个空行分隔；以换行收尾。
    blocks = ["\n".join(section) for section in sections]
    return "\n\n".join(blocks) + "\n"
