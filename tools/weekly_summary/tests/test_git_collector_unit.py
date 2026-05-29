"""Git_Collector 单元测试（Task 4.4，Req 2.3、2.5）。

针对具体示例与边界，补充属性测试（``test_git_collector_props.py``）之外的两类行为：

- **Req 2.3（非 git 路径告警并继续）**：当仓库列表中混入一个不是有效 git 仓库的
  路径时，``collect_commits`` 应为该路径产出一条**标识该路径**的
  :class:`CollectorWarning`，并**继续处理**列表中其余有效仓库（其提交照常采集）。
- **Req 2.5（窗内空提交返回空集合）**：当某个有效仓库在 Week_Window 内没有任何提交
  时，``collect_commits`` 应为该仓库返回 ``commits`` 为空的 :class:`RepoCommits`，
  且不产生错误、不产生警告。

测试在临时目录内创建**真实** git 仓库（``git init`` + 受控提交日期），git 身份与
配置通过隔离的环境变量注入，避免依赖用户全局/系统 git 配置。提交时间通过
``GIT_AUTHOR_DATE`` / ``GIT_COMMITTER_DATE`` 精确控制（二者一致，因为
``git log --since/--until`` 基于 committer date 过滤）。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timedelta

from weekly_summary.collectors import CollectorWarning
from weekly_summary.collectors.git_collector import collect_commits
from weekly_summary.week_window import week_window_for


def _git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """构造隔离的 git 环境：屏蔽用户全局/系统配置，注入确定的身份。"""
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_AUTHOR_NAME"] = "Test"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    if extra:
        env.update(extra)
    return env


def _init_repo(repo_path: str) -> None:
    """在 ``repo_path`` 初始化一个空 git 仓库（默认分支 main）。"""
    os.makedirs(repo_path, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", repo_path],
        env=_git_env(),
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo_path: str, subject: str, moment: datetime) -> None:
    """在 ``repo_path`` 创建一条空提交，精确控制提交时间。"""
    stamp = moment.isoformat()
    subprocess.run(
        ["git", "-C", repo_path, "commit", "-q", "--allow-empty", "-m", subject],
        env=_git_env({"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}),
        check=True,
        capture_output=True,
        text=True,
    )


# 选用一个固定的、确定的 ISO 周作为时间窗（周一 00:00:00 ~ 周日 23:59:59）。
_WINDOW = week_window_for(2026, 22)


def test_non_git_path_warns_and_continues() -> None:
    """Req 2.3：非 git 路径产出标识该路径的警告，并继续处理其余有效仓库。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 一个普通空目录（非 git 仓库）。
        non_git_path = os.path.join(tmp_dir, "not-a-repo")
        os.makedirs(non_git_path, exist_ok=True)

        # 一个有效 git 仓库，含一条窗内提交。
        valid_repo = os.path.join(tmp_dir, "valid-repo")
        _init_repo(valid_repo)
        in_window = _WINDOW.start + timedelta(days=1, hours=12)
        _commit(valid_repo, "fix: 修复登录跳转", in_window)

        # 非 git 路径排在有效仓库之前，验证遇到告警后仍继续处理后续仓库。
        repo_commits, warnings = collect_commits(
            [non_git_path, valid_repo], _WINDOW, None
        )

    # 恰有一条警告，且为 CollectorWarning。
    assert len(warnings) == 1
    warning = warnings[0]
    assert isinstance(warning, CollectorWarning)
    # 警告标识出了那个非 git 路径（Req 2.3：标识该路径）。
    assert warning.source == non_git_path
    assert non_git_path in warning.source
    assert warning.message  # 含人类可读说明

    # 非 git 路径不产出 RepoCommits 条目；有效仓库仍被处理（继续）。
    assert len(repo_commits) == 1
    rc = repo_commits[0]
    assert rc.repo_id == os.path.basename(valid_repo)
    assert rc.repo_path == valid_repo
    # 有效仓库的窗内提交被正常采集。
    assert [c.subject for c in rc.commits] == ["fix: 修复登录跳转"]


def test_repo_with_no_commits_in_window_returns_empty_without_error() -> None:
    """Req 2.5：窗内无提交的仓库返回空 commits 集合，且不产生错误/警告。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = os.path.join(tmp_dir, "quiet-repo")
        _init_repo(repo_path)
        # 仅有一条**窗外**提交（窗起始前 10 天），故窗内应为空。
        out_of_window = _WINDOW.start - timedelta(days=10)
        _commit(repo_path, "chore: 历史提交", out_of_window)

        repo_commits, warnings = collect_commits([repo_path], _WINDOW, None)

    # 有效仓库不产生警告（空提交不是错误，Req 2.5）。
    assert warnings == []
    # 仓库存在 -> 恰有一个 RepoCommits 条目，且 commits 为空集合。
    assert len(repo_commits) == 1
    rc = repo_commits[0]
    assert rc.repo_id == os.path.basename(repo_path)
    assert rc.repo_path == repo_path
    assert rc.commits == []
