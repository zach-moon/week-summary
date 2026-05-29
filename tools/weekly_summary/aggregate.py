"""Report_Aggregator（``aggregate.py``）— Req 5。

职责：把 Git_Collector 产出的提交集合与 Codex_Collector 产出的会话集合，按
**配置中的项目目录**聚合、统计并排序，组装为 :class:`AggregatedReport`。

设计依据：design.md「Components and Interfaces / Report_Aggregator（`aggregate.py`）— Req 5」。

聚合规则：

- 为配置（``config.repos``）中**每个**项目目录建立一个
  :class:`ProjectDistribution` 条目，包含 commit / session 均为零的项目（Req 5.1）。
- **项目归属逻辑**（保证 commit 与 codex 会话落入同一组项目桶）：
  - Git 提交天然属于其所在仓库 ``path``，按 :class:`RepoCommits` 的 ``repo_path``
    与配置仓库路径做归一化后匹配入桶。
  - Codex 会话的 ``project_dir``（即 ``session_meta.payload.cwd``）与每个配置仓库
    路径做**路径归一化 + 最长前缀匹配**（``cwd == path`` 或 ``cwd`` 位于 ``path``
    子树下）；命中多个时取最长匹配前缀（most-specific）。
  - 未匹配任何配置仓库的活动，归入保留桶 :data:`UNMATCHED_PROJECT`
    （``"__unmatched__"``，展示名「未归类」），保证统计不丢失且不污染配置项目分布。
- 计算各项目的 ``commit_count`` / ``session_count``，以及汇总 ``total_commits`` /
  ``total_sessions`` / ``total_user_prompts``（Req 5.2）。
- ``distribution`` 按 ``(commit_count, session_count)`` 降序排序（Req 5.3）；以
  ``project_dir`` 升序作为稳定次序的最终决胜键，确保输出确定可复现。

关于 :data:`UNMATCHED_PROJECT` 桶的取舍：保留桶**仅在其有实际活动**（commit 数或
session 数大于零）时才作为一条 :class:`ProjectDistribution` 出现，从而既不丢失统计、
又不在没有未归类活动时凭空多出一行污染配置项目分布。
"""

from __future__ import annotations

import os

from .models import (
    AggregatedReport,
    CodexSession,
    Config,
    ProjectDistribution,
    RepoCommits,
    WeekWindow,
)

__all__ = ["aggregate", "UNMATCHED_PROJECT"]

# 未匹配任何配置仓库的活动归入的保留桶标识（展示名「未归类」）。
UNMATCHED_PROJECT = "__unmatched__"


def _normalize(path: str) -> str:
    """对路径做归一化以便比较：展开 ``~`` 并折叠 ``.`` / ``..`` 与多余分隔符。

    不做 ``realpath`` 解析（避免触碰文件系统、不依赖路径真实存在），仅做纯字符串
    层面的归一化，足以支撑同一组配置路径与会话 ``cwd`` 之间的前缀匹配。
    """
    return os.path.normpath(os.path.expanduser(path))


def _is_within(child: str, parent: str) -> bool:
    """判断归一化后的 ``child`` 是否等于 ``parent`` 或位于其子树下。

    采用带分隔符的前缀判断（``parent + os.sep``），避免 ``/a/foo`` 被误判为
    ``/a/foobar`` 的子路径。
    """
    if child == parent:
        return True
    parent_with_sep = parent if parent.endswith(os.sep) else parent + os.sep
    return child.startswith(parent_with_sep)


def _match_project(
    target: str, normalized_projects: list[tuple[str, str]]
) -> str | None:
    """把 ``target`` 路径归属到最长前缀匹配的配置项目，返回其原始 project_dir。

    Args:
        target: 待归属的路径（commit 的 ``repo_path`` 或会话的 ``project_dir``）。
        normalized_projects: ``(归一化路径, 原始 project_dir)`` 列表。

    Returns:
        命中的配置项目原始 ``project_dir``；命中多个时取归一化路径最长者
        （most-specific）；无命中返回 ``None``。
    """
    normalized_target = _normalize(target)
    best_project: str | None = None
    best_len = -1
    for normalized_path, original in normalized_projects:
        if _is_within(normalized_target, normalized_path) and len(normalized_path) > best_len:
            best_project = original
            best_len = len(normalized_path)
    return best_project


def aggregate(
    config: Config,
    window: WeekWindow,
    repo_commits: list[RepoCommits],
    sessions: list[CodexSession],
) -> AggregatedReport:
    """聚合提交与会话为按项目分布的 :class:`AggregatedReport`（Req 5）。

    Args:
        config: 配置对象，``config.repos`` 决定项目桶集合（Req 5.1）。
        window: 时间窗，用于派生 ``report_identifier`` 与起止日期。
        repo_commits: 各仓库时间窗内的提交集合。
        sessions: 时间窗内的 Codex 会话集合。

    Returns:
        含已排序 ``distribution``（含零活动项目）、透传的 ``repo_commits`` /
        ``repo_sessions`` 与三类汇总数字的 :class:`AggregatedReport`；
        ``llm_suggestions`` 置为 ``None``（LLM 为后续任务）。
    """
    # 1) 为每个配置项目建桶（按配置顺序，按归一化路径去重）。
    project_order: list[str] = []
    commit_counts: dict[str, int] = {}
    session_counts: dict[str, int] = {}
    normalized_projects: list[tuple[str, str]] = []
    seen_normalized: set[str] = set()

    for repo in config.repos:
        normalized = _normalize(repo)
        if normalized in seen_normalized:
            # 多个配置项归一化到同一路径时只保留首个，避免重复桶。
            continue
        seen_normalized.add(normalized)
        project_order.append(repo)
        commit_counts[repo] = 0
        session_counts[repo] = 0
        normalized_projects.append((normalized, repo))

    # 2) Git 提交按仓库路径归属入桶；未匹配计入保留桶。
    unmatched_commits = 0
    for rc in repo_commits:
        count = len(rc.commits)
        if count == 0:
            continue
        matched = _match_project(rc.repo_path, normalized_projects)
        if matched is not None:
            commit_counts[matched] += count
        else:
            unmatched_commits += count

    # 3) Codex 会话按 cwd 最长前缀匹配归属入桶；未匹配计入保留桶。
    unmatched_sessions = 0
    for session in sessions:
        matched = _match_project(session.project_dir, normalized_projects)
        if matched is not None:
            session_counts[matched] += 1
        else:
            unmatched_sessions += 1

    # 4) 组装 distribution 条目（含零活动项目，Req 5.1）。
    distribution = [
        ProjectDistribution(
            project_dir=project,
            commit_count=commit_counts[project],
            session_count=session_counts[project],
        )
        for project in project_order
    ]

    # 保留桶仅在确有未归类活动时才作为一条分布出现，避免污染配置项目分布。
    if unmatched_commits > 0 or unmatched_sessions > 0:
        distribution.append(
            ProjectDistribution(
                project_dir=UNMATCHED_PROJECT,
                commit_count=unmatched_commits,
                session_count=unmatched_sessions,
            )
        )

    # 5) 按 (commit_count, session_count) 降序排序；project_dir 升序作为确定性决胜键（Req 5.3）。
    distribution.sort(
        key=lambda d: (-d.commit_count, -d.session_count, d.project_dir)
    )

    # 6) 汇总数字（Req 5.2）。
    total_commits = sum(len(rc.commits) for rc in repo_commits)
    total_sessions = len(sessions)
    total_user_prompts = sum(session.prompt_count for session in sessions)

    return AggregatedReport(
        report_identifier=window.report_identifier,
        week_start=window.start.date(),
        week_end=window.end.date(),
        distribution=distribution,
        repo_commits=repo_commits,
        repo_sessions=sessions,
        total_commits=total_commits,
        total_sessions=total_sessions,
        total_user_prompts=total_user_prompts,
        llm_suggestions=None,
    )
