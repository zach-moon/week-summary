"""Git_Collector 作者过滤属性测试（Task 4.3 / Property 3）。

本文件实现单条 Correctness Property：

- **Property 3**（Req 2.4）：对一组多作者的随机提交与一个作者过滤条件，
  ``collect_commits`` 返回的所有提交都应属于该作者（即恰好等于该作者的提交集合，
  其余作者被排除）。

实现手段：在临时目录内创建**真实** git 仓库（``git init`` + 受控提交），通过环境变量
``GIT_AUTHOR_NAME`` / ``GIT_AUTHOR_EMAIL`` 为每条提交指定作者，并用
``GIT_AUTHOR_DATE`` / ``GIT_COMMITTER_DATE`` 精确控制提交时间。全部提交都落在**同一**
周窗内且时间单调递增，因此唯一生效的过滤条件就是 ``--author`` 作者过滤——把作者过滤的
效果从时间窗过滤中隔离出来。

字段说明：:class:`weekly_summary.models.Commit` **不保留作者**字段，故对「所有返回提交
都属于目标作者」的断言改为对**提交标题集合**做断言——返回的 subject 集合应恰好等于目标
作者所提交的 subject 集合（每个 subject 以 ``c{i}-`` 前缀保证唯一，可无歧义回映）。

迭代次数：本属性测试至少运行 100 次随机迭代（Hypothesis ``max_examples>=100``，由
``conftest.py`` 的 ``weekly-summary`` profile 提供；本文件不在本地下调该值）。git 子进程
I/O 较慢，故 ``deadline=None`` 关闭单例时限。

为避免 ``@given`` 与 pytest 函数级 fixture（如 ``tmp_path``）同用而触发 Hypothesis 的
``function_scoped_fixture`` 健康检查，仓库一律在每个示例内用
:func:`tempfile.TemporaryDirectory` 创建。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import date, datetime, timedelta

import hypothesis.strategies as st
from hypothesis import given, settings

from weekly_summary.collectors.git_collector import collect_commits
from weekly_summary.week_window import week_window_for

# 年份范围：避开 32 位 time_t 与极端边界，确保 git / astimezone 稳定。
_MIN_YEAR = 2001
_MAX_YEAR = 2098

# 提交标题字符集：可见非空白字符（含 CJK），排除控制 / 格式 / 行分隔等类别，
# 保证 subject 经 git 规范化（裁剪行尾空白、仅取首行）后保持不变、且非空白。
_subject_char = st.characters(
    min_codepoint=33,
    max_codepoint=0x9FFF,
    blacklist_categories=("Cc", "Cf", "Cs", "Zl", "Zp"),
)
_subject_text = st.text(alphabet=_subject_char, min_size=1, max_size=8)

# 作者集合：名字与邮箱互不为子串，避免 git ``--author`` 正则跨作者误命中。
_AUTHORS = (
    ("Alice", "alice@example.com"),
    ("Bob", "bob@example.com"),
    ("Carol", "carol@example.com"),
)


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
    author: tuple[str, str],
) -> None:
    """在 ``repo_path`` 创建一条空提交，精确控制时间与作者。"""
    stamp = moment.isoformat()
    extra = {
        "GIT_AUTHOR_DATE": stamp,
        "GIT_COMMITTER_DATE": stamp,
        "GIT_AUTHOR_NAME": author[0],
        "GIT_AUTHOR_EMAIL": author[1],
    }
    subprocess.run(
        ["git", "-C", repo_path, "commit", "-q", "--allow-empty", "-m", subject],
        env=_git_env(extra),
        check=True,
        capture_output=True,
        text=True,
    )


@st.composite
def _author_plan(draw: st.DrawFn):
    """生成 ``(window, specs, target_email)``。

    - ``window``：由随机基准日期推出的某一周时间窗。
    - ``specs``：``(datetime, subject, author)`` 列表；全部提交落在同一周窗内、时间
      单调递增（周二起按小时累加），从而把作者过滤从时间窗过滤中隔离出来。
    - ``target_email``：作为 ``--author`` 过滤条件的目标作者邮箱（可能没有任何提交，
      此时期望返回空集合——这是合法且需覆盖的边界）。
    """
    base = draw(
        st.dates(min_value=date(_MIN_YEAR, 1, 1), max_value=date(_MAX_YEAR, 12, 1))
    )
    iso = base.isocalendar()
    window = week_window_for(iso.year, iso.week)

    n = draw(st.integers(min_value=1, max_value=6))
    specs: list[tuple[datetime, str, tuple[str, str]]] = []
    for i in range(n):
        author = draw(st.sampled_from(_AUTHORS))
        # 周二起按小时递增（i <= 5），确保落在窗内且时间单调。
        moment = window.start + timedelta(days=1, hours=i)
        subject = f"c{i}-" + draw(_subject_text)
        specs.append((moment, subject, author))

    target = draw(st.sampled_from(_AUTHORS))
    return window, specs, target[1]


@settings(deadline=None)  # git 子进程 I/O 较慢，关闭单例时限；迭代次数沿用 profile 的 100
@given(plan=_author_plan())
def test_property_3_git_author_filter(plan) -> None:
    # Feature: weekly-dev-report, Property 3: Git 作者过滤
    """**Validates: Requirements 2.4**

    指定作者过滤条件时，``collect_commits`` 返回的提交应恰好等于该作者的提交集合
    （其余作者被排除）。由于 :class:`Commit` 不保留作者字段，以「提交标题集合相等」
    作为等价判据。
    """
    window, specs, target_email = plan
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = os.path.join(tmp_dir, "myrepo")
        _init_repo(repo_path)
        for moment, subject, author in specs:
            _commit(repo_path, subject, moment, author=author)

        repo_commits, warnings = collect_commits([repo_path], window, target_email)

    # 有效 git 仓库不应产生警告。
    assert warnings == []

    returned_subjects = {c.subject for rc in repo_commits for c in rc.commits}
    expected_subjects = {
        subject for _, subject, author in specs if author[1] == target_email
    }
    # 返回集合恰好等于目标作者的提交集合：既无遗漏（目标作者全采），也无多采（其余排除）。
    assert returned_subjects == expected_subjects
