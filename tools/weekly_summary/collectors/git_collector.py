"""Git_Collector（``collectors/git_collector.py``）— Req 2。

职责：对配置中的每个仓库运行时间窗内的 ``git log``，解析提交记录为 :class:`Commit`，
并按仓库分组为 :class:`RepoCommits`。

实现要点（对应设计「Components and Interfaces / Git_Collector」）：

- 使用 ``git -C <repo> log --since=<start> --until=<end>
  --pretty=format:%H%x1f%ad%x1f%s --date=short``。其中 ``%x1f`` 为 ASCII 单元
  分隔符（0x1f），用作字段分隔，避免 subject 中的字符与分隔符冲突（Req 2.1、2.2）。
- ``author`` 非空时追加 ``--author=<author>`` 做作者过滤（Req 2.4）。
- 非 git 路径：``git`` 以非零码退出（如 ``fatal: not a git repository``），
  产出一条标识该路径的 :class:`CollectorWarning` 并继续处理其余仓库（Req 2.3）。
- 时间窗内无提交：返回 ``commits`` 为空的 :class:`RepoCommits`，不报错（Req 2.5）。
- ``repo_id`` 取仓库路径的 basename。
"""

from __future__ import annotations

import os
import subprocess
from datetime import date

from ..models import Commit, RepoCommits, WeekWindow
from . import CollectorWarning

__all__ = ["collect_commits", "FIELD_SEP"]

# ASCII 单元分隔符（0x1f）。git ``--pretty=format`` 中以 ``%x1f`` 产出该字节，
# 用作 hash / date / subject 三字段之间的分隔符，避免 subject 文本冲突。
FIELD_SEP = "\x1f"

# git log 的 pretty 格式：<hash>\x1f<date(YYYY-MM-DD)>\x1f<subject>
_PRETTY_FORMAT = f"format:%H{FIELD_SEP}%ad{FIELD_SEP}%s"


def _repo_id(repo_path: str) -> str:
    """由仓库路径取 basename 作为仓库标识（Req 2.2）。"""
    return os.path.basename(os.path.normpath(repo_path))


def _build_git_args(repo: str, window: WeekWindow, author: str | None) -> list[str]:
    """构造 ``git log`` 命令行参数（含时间窗与可选作者过滤）。"""
    args = [
        "git",
        "-C",
        repo,
        "log",
        f"--since={window.start.isoformat()}",
        f"--until={window.end.isoformat()}",
        f"--pretty={_PRETTY_FORMAT}",
        "--date=short",
    ]
    if author:  # Req 2.4：仅在提供作者过滤时追加
        args.append(f"--author={author}")
    return args


def _parse_commits(repo_id: str, stdout: str) -> list[Commit]:
    """把 ``git log`` 输出解析为 :class:`Commit` 列表。

    每行形如 ``<hash>\\x1f<YYYY-MM-DD>\\x1f<subject>``。空输出返回空列表（Req 2.5）。
    """
    commits: list[Commit] = []
    for line in stdout.splitlines():
        if not line:
            continue
        parts = line.split(FIELD_SEP, 2)
        if len(parts) != 3:
            # 防御性：格式不符的行跳过（正常 git 输出不会触发）。
            continue
        _hash, date_str, subject = parts
        try:
            commit_date = date.fromisoformat(date_str)
        except ValueError:
            # 日期无法解析则跳过该行，避免污染结果。
            continue
        commits.append(Commit(repo_id=repo_id, date=commit_date, subject=subject))
    return commits


def collect_commits(
    repos: list[str],
    window: WeekWindow,
    author: str | None,
) -> tuple[list[RepoCommits], list[CollectorWarning]]:
    """采集每个仓库在 Week_Window 内的提交记录（Req 2）。

    Args:
        repos:  仓库绝对路径列表。
        window: 本周时间窗（提供 ``start`` / ``end``）。
        author: 作者过滤条件；为 ``None`` 或空串时不过滤（Req 2.4）。

    Returns:
        二元组 ``(repo_commits, warnings)``：

        - ``repo_commits``：每个仓库一个 :class:`RepoCommits`（窗内无提交则
          ``commits`` 为空，Req 2.5）。非 git 仓库不产出 :class:`RepoCommits` 条目。
        - ``warnings``：非致命警告列表；非 git 路径会在此各产出一条（Req 2.3）。
    """
    repo_commits: list[RepoCommits] = []
    warnings: list[CollectorWarning] = []

    for repo in repos:
        repo_id = _repo_id(repo)
        args = _build_git_args(repo, window, author)
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            # 无法执行 git（如路径不可访问 / git 不可用）：标识该路径并继续。
            warnings.append(
                CollectorWarning(
                    source=repo,
                    message=f"无法对路径执行 git：{exc}",
                )
            )
            continue

        if result.returncode != 0:
            # 非 git 仓库或其它 git 错误：记录标识该路径的警告并继续（Req 2.3）。
            detail = result.stderr.strip() or f"git 退出码 {result.returncode}"
            warnings.append(
                CollectorWarning(
                    source=repo,
                    message=f"路径不是有效的 git 仓库或 git 执行失败：{detail}",
                )
            )
            continue

        commits = _parse_commits(repo_id, result.stdout)
        repo_commits.append(
            RepoCommits(repo_id=repo_id, repo_path=repo, commits=commits)
        )

    return repo_commits, warnings
