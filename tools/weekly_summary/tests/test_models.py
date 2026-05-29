"""数据模型冒烟测试（Task 1.1）。

验证 ``models.py`` 中全部 dataclass 能够正确导入、实例化，并保留字段值。
这同时确认包结构可被 pytest 干净导入（``pythonpath = ["tools"]``）。
"""

from __future__ import annotations

from datetime import date, datetime

from weekly_summary.models import (
    AggregatedReport,
    CodexSession,
    Commit,
    Config,
    FeishuConfig,
    LLMConfig,
    ProjectDistribution,
    RepoCommits,
    WeekWindow,
)


def test_config_defaults() -> None:
    """Config 的默认值符合设计（LLM 默认关闭等，Req 8.2）。"""
    cfg = Config(repos=["/Users/me/Projects/a"])
    assert cfg.repos == ["/Users/me/Projects/a"]
    assert cfg.output_dir == "dev_log"
    assert cfg.author is None
    assert cfg.export_enabled is True
    assert cfg.push_target is None
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.llm.enabled is False  # Req 8.2
    assert isinstance(cfg.feishu, FeishuConfig)
    assert cfg.feishu.enabled is False


def test_llm_and_feishu_config() -> None:
    llm = LLMConfig(enabled=True, provider="anthropic", model="claude")
    assert (llm.enabled, llm.provider, llm.model) == (True, "anthropic", "claude")

    feishu = FeishuConfig(enabled=True, webhook_url="https://example.com/hook")
    assert feishu.enabled is True
    assert feishu.webhook_url == "https://example.com/hook"


def test_week_window_fields() -> None:
    start = datetime(2026, 5, 25, 0, 0, 0)
    end = datetime(2026, 5, 31, 23, 59, 59)
    ww = WeekWindow(start=start, end=end, report_identifier="2026-W22")
    assert ww.start == start
    assert ww.end == end
    assert ww.report_identifier == "2026-W22"


def test_commit_and_repo_commits() -> None:
    commit = Commit(repo_id="project-a", date=date(2026, 5, 26), subject="Add login route")
    assert commit.repo_id == "project-a"
    assert commit.date == date(2026, 5, 26)
    assert commit.subject == "Add login route"

    repo = RepoCommits(repo_id="project-a", repo_path="/Users/me/Projects/a", commits=[commit])
    assert repo.commits[0] is commit
    # 时间窗内可能为空（Req 2.5）
    assert RepoCommits(repo_id="b", repo_path="/p/b", commits=[]).commits == []


def test_codex_session() -> None:
    session = CodexSession(
        session_id="abc-123",
        project_dir="/Users/me/Projects/a",
        date=date(2026, 5, 26),
        user_prompts=["如何保护路由？", "怎么做 oauth 回调？"],
        prompt_count=2,
    )
    assert session.prompt_count == len(session.user_prompts)


def test_aggregated_report() -> None:
    dist = ProjectDistribution(project_dir="/p/a", commit_count=12, session_count=4)
    report = AggregatedReport(
        report_identifier="2026-W22",
        week_start=date(2026, 5, 25),
        week_end=date(2026, 5, 31),
        distribution=[dist],
        repo_commits=[],
        repo_sessions=[],
        total_commits=12,
        total_sessions=4,
        total_user_prompts=37,
    )
    assert report.distribution[0].commit_count == 12
    assert report.llm_suggestions is None  # 默认无 LLM 章节
