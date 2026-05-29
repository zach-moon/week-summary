"""Git_Collector 时间窗与字段保留属性测试（Task 4.2 / Property 2）。

实现 Git_Collector 组件的一条 Correctness Property：

- **Property 2**（Req 2.1、2.2）：对一组带随机提交日期的提交与一个 Week_Window,
  ``collect_commits`` 返回的每条提交日期都落在 ``[window.start, window.end]`` 内，
  窗内提交都被采集，且每条结果保留 ``repo_id`` / ``date`` / ``subject``（值与源一致）。

（Property 3「Git 作者过滤」按「每个属性一个文件」的约定独立于
``test_git_collector_author_props.py`` 实现。）

实现手段：在临时目录内创建**真实** git 仓库（``git init`` + 受控提交日期），
通过环境变量 ``GIT_AUTHOR_DATE`` / ``GIT_COMMITTER_DATE`` 精确控制每条提交的时间
（二者一致，因为 ``git log --since/--until`` 基于 *committer date* 过滤，而
``--date=short`` 展示 *author date*）。提交按时间升序创建，使线性历史在时间上单调，
避免 ``git log --since`` 的遍历剪枝造成漏采。

git I/O 较慢，故对本文件的属性测试使用本地 ``@settings(max_examples=25,
deadline=None)``（在此处放宽迭代次数是可接受的——原因是真实 git 子进程开销）。

为避免 ``@given`` 与 pytest 函数级 fixture（如 ``tmp_path``）同用触发 Hypothesis
的 ``function_scoped_fixture`` 健康检查，仓库一律在每个示例内用
:func:`tempfile.TemporaryDirectory` 创建。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, date, timedelta

import hypothesis.strategies as st
from hypothesis import given, settings

from weekly_summary.collectors.git_collector import collect_commits
from weekly_summary.week_window import week_window_for

# 年份范围：避开 32 位 time_t 与极端边界，确保 git / astimezone 稳定。
_MIN_YEAR = 2001
_MAX_YEAR = 2098

# 提交标题字符集：可见非空白字符（含 CJK），排除控制 / 格式 / 行分隔等类别。
# git 会对提交标题做规范化（裁剪行尾空白、规范化部分控制字符、仅取首行），故
# 生成的 subject 必须是「单行、无控制字符」的真实文本，否则回读会被 git 改写
# （例如 "c0-\x85" 会被裁成 "c0-"）。min_codepoint=33 已排除空格与 ASCII 控制；
# 这里再排除 C1 控制（Cc）、格式字符（Cf）、代理区（Cs）、行 / 段分隔符（Zl/Zp），
# 从而保证 subject 经 git 规范化后保持不变、且非空白。
_subject_char = st.characters(
    min_codepoint=33,
    max_codepoint=0x9FFF,
    blacklist_categories=("Cc", "Cf", "Cs", "Zl", "Zp"),
)
_subject_text = st.text(alphabet=_subject_char, min_size=1, max_size=8)


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


def _commit(
    repo_path: str,
    subject: str,
    moment: datetime,
) -> None:
    """在 ``repo_path`` 创建一条空提交，精确控制时间。"""
    stamp = moment.isoformat()
    extra = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    subprocess.run(
        ["git", "-C", repo_path, "commit", "-q", "--allow-empty", "-m", subject],
        env=_git_env(extra),
        check=True,
        capture_output=True,
        text=True,
    )


@st.composite
def _commit_plan(draw: st.DrawFn):
    """生成 ``(window, specs)``；specs 为 ``(datetime, subject, in_window)`` 列表。

    窗内时间取 ``start + [1, 5] 天 + 任意时分``（落在周二 00:00 至周六 23:59，安全
    内含）；窗外时间在窗前/窗后至少一天的正午（远离边界），故 ``in_window`` 标记与
    实际日期归属一致。subject 以 ``c{i}-`` 前缀保证唯一，便于回映。
    """
    base = draw(st.dates(min_value=date(_MIN_YEAR, 1, 1), max_value=date(_MAX_YEAR, 12, 1)))
    iso = base.isocalendar()
    window = week_window_for(iso.year, iso.week)

    n = draw(st.integers(min_value=1, max_value=6))
    specs: list[tuple[datetime, str, bool]] = []
    for i in range(n):
        in_window = draw(st.booleans())
        if in_window:
            day_off = draw(st.integers(min_value=1, max_value=5))
            hour = draw(st.integers(min_value=0, max_value=23))
            minute = draw(st.integers(min_value=0, max_value=59))
            moment = window.start + timedelta(days=day_off, hours=hour, minutes=minute)
        else:
            day_off = draw(st.integers(min_value=1, max_value=30))
            if draw(st.booleans()):
                moment = window.start - timedelta(days=day_off) + timedelta(hours=12)
            else:
                moment = window.end + timedelta(days=day_off) - timedelta(hours=12)
        subject = f"c{i}-" + draw(_subject_text)
        specs.append((moment, subject, in_window))
    return window, specs


@settings(max_examples=25, deadline=None)  # git 子进程 I/O 较慢，放宽迭代次数
@given(plan=_commit_plan())
def test_property_2_git_window_and_field_preservation(plan) -> None:
    # Feature: weekly-dev-report, Property 2: Git 采集落在时间窗内且保留字段
    """**Validates: Requirements 2.1, 2.2**

    窗内提交都应被采集；返回的每条提交日期落在 ``[start.date, end.date]`` 内；
    ``repo_id``（仓库 basename）、``date``、``subject`` 三字段值与源一致。
    """
    window, specs = plan
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = os.path.join(tmp_dir, "myrepo")
        _init_repo(repo_path)
        # 按时间升序创建，保证线性历史在时间上单调（避免 --since 遍历剪枝漏采）。
        for moment, subject, _ in sorted(specs, key=lambda s: s[0]):
            _commit(repo_path, subject, moment)

        repo_commits, warnings = collect_commits([repo_path], window, None)

    # 有效 git 仓库不应产生警告。
    assert warnings == []
    # 仓库存在则恰有一个 RepoCommits 条目。
    assert len(repo_commits) == 1
    rc = repo_commits[0]
    assert rc.repo_id == os.path.basename(repo_path)
    assert rc.repo_path == repo_path

    returned = rc.commits
    returned_subjects = {c.subject for c in returned}
    expected_subjects = {subject for _, subject, in_window in specs if in_window}

    # 窗内提交都被采集，且未采集窗外提交。
    assert returned_subjects == expected_subjects

    date_by_subject = {subject: moment.date() for moment, subject, _ in specs}
    for commit in returned:
        # repo_id 保留为 basename。
        assert commit.repo_id == os.path.basename(repo_path)
        # date 落在时间窗内（按日期）。
        assert window.start.date() <= commit.date <= window.end.date()
        # date / subject 值与源一致。
        assert commit.date == date_by_subject[commit.subject]
