"""summarize.py 编排层单元 + 集成测试（Tasks 13.3、13.4）。

覆盖编排层的核心行为（Req 7.3、7.4、7.5、7.6、11.1、11.2、11.3）：

- **集成 / 11.1、7.1**：一次完整运行同时产出 ``<outdir>/<id>.md`` 与
  ``<outdir>/data/<id>.json``，退出码 0（Req 11.2）。包含一条**端到端**集成测试
  （Task 13.4）：用真实临时 git 仓库（受控提交日期）+ 真实 Codex ``rollout-*.jsonl``
  会话日志跑完整默认流程，断言两个产出文件均生成，且 Markdown / JSON 如实反映
  fixture 的提交标题、关键问题与分布 / 汇总数字。
- **Req 7.5（非交互式跳过覆盖）**：目标已存在且非交互式且无 ``--yes`` → 跳过覆盖、
  保留原文件、打印「已跳过覆盖」，退出码仍为 0。
- **Req 7.4（强制覆盖）**：``--yes`` → 覆盖已存在文件。
- **Req 11.3（不可恢复错误）**：配置缺失 → 非零退出并打印错误；非法 ``--week`` →
  非零退出（参数错误）。

隐私 / 零外发：临时配置中 ``llm.enabled`` 与 ``feishu.enabled`` 均为 ``False``，
因此整条流程不发起任何外部网络请求。Codex 采集根目录被重定向到临时目录（默认空目录，
端到端测试中则重定向到 fixture 会话目录），使运行与本机真实 ``~/.codex`` 完全隔离、
结果确定可复现。端到端测试中的 git 仓库亦在隔离的 git 环境（屏蔽全局 / 系统配置、
注入确定身份与提交时间）中创建，无网络、不依赖本机 git 全局配置。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from weekly_summary import summarize
from weekly_summary.collectors.codex_collector import collect_sessions as _real_collect

_WEEK = "2026-W22"
_CONFIG_TOML = """\
output_dir = "dev_log"
export_enabled = true
repos = []

[llm]
enabled = false

[feishu]
enabled = false
"""


@pytest.fixture(autouse=True)
def hermetic_codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把 Codex 采集根目录重定向到一个不存在的临时目录，隔离真实 ~/.codex。"""
    empty_root = tmp_path / "no-codex"

    def _isolated_collect(window, root=empty_root):
        return _real_collect(window, root=root)

    monkeypatch.setattr(summarize, "collect_sessions", _isolated_collect)


def _write_config(tmp_path: Path) -> str:
    cfg_path = tmp_path / "weekly-summary.toml"
    cfg_path.write_text(_CONFIG_TOML, encoding="utf-8")
    return str(cfg_path)


def _force_non_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """确保 sys.stdin.isatty() 返回 False（非交互式路径，Req 7.5）。"""

    class _FakeStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", _FakeStdin())


def _force_interactive(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    """模拟交互式 tty 并让 input() 返回指定应答（Req 7.3）。

    使 ``sys.stdin.isatty()`` 返回 ``True`` 触发交互式覆盖确认分支，并把内建
    ``input`` 替换为返回固定 ``answer`` 的桩，避免真实阻塞读取标准输入。
    """

    class _FakeStdin:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", _FakeStdin())
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: answer)


# --------------------------------------------------------------------------- #
# 13.4 集成 + 11.1 / 7.1 / 11.2：完整运行产出 .md 与 .json
# --------------------------------------------------------------------------- #
def test_full_run_writes_md_and_json_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Req 11.1/7.1/11.2：完整运行产出 .md 与 .json，退出码 0。"""
    cfg = _write_config(tmp_path)
    outdir = tmp_path / "out"

    code = summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK])

    assert code == 0  # Req 11.2

    md_file = outdir / f"{_WEEK}.md"
    json_file = outdir / "data" / f"{_WEEK}.json"
    assert md_file.is_file()  # Req 7.1
    assert json_file.is_file()  # Req 11.1 / 10.1

    md_text = md_file.read_text(encoding="utf-8")
    assert _WEEK in md_text  # 标题含 Report_Identifier

    import json as _json

    data = _json.loads(json_file.read_text(encoding="utf-8"))
    assert data["report_identifier"] == _WEEK

    # 成功写入后打印绝对路径（Req 7.6）。
    out = capsys.readouterr().out
    assert str(md_file.resolve()) in out


# --------------------------------------------------------------------------- #
# 13.4 端到端集成（Req 11.1）：真实 fixture git 仓库 + Codex 日志跑完整默认流程
# --------------------------------------------------------------------------- #
# W22 时间窗：2026-05-25 00:00:00 ~ 2026-05-31 23:59:59（本地时区）。窗内时间用于
# 放置 fixture 提交与会话；下方时间戳均落在该区间内。
_E2E_COMMIT_DT = datetime(2026, 5, 27, 10, 0, 0)  # 周三 10:00，稳居窗内
# Codex 会话时间戳为 UTC（带 Z）。取本地正午对应的 UTC 时刻，确保任意本地时区下
# 转回本地后仍落在 [周一 00:00, 周日 23:59:59] 内（远离两端边界）。
_E2E_SESSION_LOCAL = datetime(2026, 5, 27, 12, 0, 0)


def _git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """构造隔离的 git 环境：屏蔽用户全局 / 系统配置，注入确定身份（无网络）。"""
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


def _init_repo(repo_path: Path) -> None:
    """在 ``repo_path`` 初始化一个空 git 仓库（默认分支 main）。"""
    repo_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo_path)],
        env=_git_env(),
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo_path: Path, subject: str, moment: datetime) -> None:
    """在 ``repo_path`` 创建一条空提交，精确控制提交时间（author == committer）。"""
    stamp = moment.isoformat()
    extra = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-q", "--allow-empty", "-m", subject],
        env=_git_env(extra),
        check=True,
        capture_output=True,
        text=True,
    )


def _write_rollout(
    codex_root: Path,
    *,
    cwd: str,
    session_local: datetime,
    real_prompts: list[str],
    injected_prompt: str | None,
    uuid: str,
) -> None:
    """写一份真实形态的 Codex ``rollout-*.jsonl`` 到 ``<root>/YYYY/MM/DD/``。

    内容包含：``session_meta``（cwd + UTC timestamp）、可选的注入上下文 user 消息
    （应被排除）、若干真实 user 提问（应保留），以及一条 assistant 回复（非 user，
    应被忽略）。时间戳写为 UTC（带 ``Z``），与真实 Codex 日志一致。
    """
    # 把本地时刻转换为 UTC 时间戳字符串（带 Z），匹配 Codex 真实写法。
    # session_local 为 naive 本地时间：先本地化（astimezone 附加本地 tz），再转 UTC。
    utc = session_local.astimezone().astimezone(timezone.utc)
    ts = utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    day_dir = codex_root / f"{session_local:%Y}" / f"{session_local:%m}" / f"{session_local:%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    file_ts = session_local.strftime("%Y-%m-%dT%H-%M-%S")
    path = day_dir / f"rollout-{file_ts}-{uuid}.jsonl"

    lines: list[str] = []
    lines.append(
        json.dumps(
            {
                "timestamp": ts,
                "type": "session_meta",
                "payload": {"id": uuid, "timestamp": ts, "cwd": cwd},
            },
            ensure_ascii=False,
        )
    )
    if injected_prompt is not None:
        lines.append(
            json.dumps(
                {
                    "timestamp": ts,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": injected_prompt}],
                    },
                },
                ensure_ascii=False,
            )
        )
    for prompt in real_prompts:
        lines.append(
            json.dumps(
                {
                    "timestamp": ts,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    },
                },
                ensure_ascii=False,
            )
        )
    # 一条 assistant 回复（role != user，应被忽略，不计入提问）。
    lines.append(
        json.dumps(
            {
                "timestamp": ts,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "好的。"}],
                },
            },
            ensure_ascii=False,
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_end_to_end_with_fixture_repos_and_codex_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Req 11.1：用真实 git 仓库 + Codex 日志跑完整默认流程，产出 .md 与 .json。

    断言：退出码 0；``<outdir>/<id>.md`` 与 ``<outdir>/data/<id>.json`` 均生成；
    Markdown 含 fixture 的提交标题与真实关键问题（且不含被注入的上下文消息）；
    JSON 的分布 / 汇总数字如实反映两个仓库的提交与一次 Codex 会话。
    """
    # 1) 两个真实临时 git 仓库，各放一条窗内提交（subject 唯一便于断言）。
    repo_alpha = tmp_path / "repos" / "alpha"
    repo_beta = tmp_path / "repos" / "beta"
    _init_repo(repo_alpha)
    _init_repo(repo_beta)

    subject_alpha = "feat: 实现 alpha 端到端提交主题"
    subject_beta = "fix: 修复 beta 模块的窗内缺陷"
    out_of_window_subject = "chore: 窗外提交不应被采集"
    # 按时间升序创建提交，保证线性历史在时间上单调，避免 git log --since 的遍历剪枝
    # 把窗内提交剪掉（窗外提交若为 HEAD 且早于 --since，git 会停止回溯其祖先）。
    _commit(repo_alpha, out_of_window_subject, _E2E_COMMIT_DT - timedelta(days=7))
    _commit(repo_alpha, subject_alpha, _E2E_COMMIT_DT)
    _commit(repo_beta, subject_beta, _E2E_COMMIT_DT + timedelta(hours=1))

    # 2) 一份真实的 Codex rollout 会话：cwd 指向 alpha 仓库，含 2 条真实提问
    #    + 1 条注入上下文消息（应被排除）。
    codex_root = tmp_path / "codex-sessions"
    real_prompts = [
        "帮我设计端到端集成测试的结构",
        "再补充对窗外提交过滤的断言",
    ]
    injected = (
        "<environment_context>\n  <cwd>"
        + str(repo_alpha)
        + "</cwd>\n</environment_context>"
    )
    _write_rollout(
        codex_root,
        cwd=str(repo_alpha),
        session_local=_E2E_SESSION_LOCAL,
        real_prompts=real_prompts,
        injected_prompt=injected,
        uuid="019e7000-aaaa-7080-834a-aedc21da9999",
    )

    # 把 Codex 采集根目录重定向到 fixture 会话目录（覆盖 autouse 的空目录隔离）。
    def _fixture_collect(window, root=codex_root):
        return _real_collect(window, root=root)

    monkeypatch.setattr(summarize, "collect_sessions", _fixture_collect)

    # 3) 写配置：repos 指向两个 fixture 仓库；llm / feishu 关闭（零外发）。
    cfg_path = tmp_path / "weekly-summary.toml"
    cfg_path.write_text(
        "output_dir = \"dev_log\"\n"
        "export_enabled = true\n"
        f"repos = [{json.dumps(str(repo_alpha))}, {json.dumps(str(repo_beta))}]\n"
        "\n[llm]\nenabled = false\n"
        "\n[feishu]\nenabled = false\n",
        encoding="utf-8",
    )

    outdir = tmp_path / "out"

    # 4) 跑完整默认流程。
    code = summarize.main(
        ["--config", str(cfg_path), "--output-dir", str(outdir), "--week", _WEEK]
    )

    assert code == 0  # Req 11.2

    # 两个产出文件均生成（Req 11.1 / 7.1 / 10.1）。
    md_file = outdir / f"{_WEEK}.md"
    json_file = outdir / "data" / f"{_WEEK}.json"
    assert md_file.is_file()
    assert json_file.is_file()

    md_text = md_file.read_text(encoding="utf-8")
    data = json.loads(json_file.read_text(encoding="utf-8"))

    # ---- Markdown 反映 fixture 提交与关键问题 ----
    assert _WEEK in md_text
    assert subject_alpha in md_text  # alpha 窗内提交标题出现
    assert subject_beta in md_text  # beta 窗内提交标题出现
    assert out_of_window_subject not in md_text  # 窗外提交被过滤
    for prompt in real_prompts:  # 真实关键问题出现在 codex 章节
        assert prompt in md_text
    assert "<environment_context>" not in md_text  # 注入上下文被排除（Req 3.4）

    # ---- JSON 汇总数字反映活动 ----
    assert data["report_identifier"] == _WEEK
    assert data["numbers"]["total_commits"] == 2  # alpha + beta 各 1（窗内）
    assert data["numbers"]["total_sessions"] == 1  # 一次 Codex 会话
    assert data["numbers"]["total_user_prompts"] == 2  # 2 条真实提问（注入被排除）

    # ---- JSON 分布反映两个项目的活动 ----
    dist = {d["project_dir"]: d for d in data["distribution"]}
    assert str(repo_alpha) in dist
    assert str(repo_beta) in dist
    # alpha：1 个 commit + 1 次会话（会话 cwd 指向 alpha）。
    assert dist[str(repo_alpha)]["commit_count"] == 1
    assert dist[str(repo_alpha)]["session_count"] == 1
    # beta：1 个 commit、无会话。
    assert dist[str(repo_beta)]["commit_count"] == 1
    assert dist[str(repo_beta)]["session_count"] == 0

    # ---- JSON repo_commits 含两仓的窗内提交标题，且不含窗外提交 ----
    all_subjects = {
        c["subject"] for rc in data["repo_commits"] for c in rc["commits"]
    }
    assert subject_alpha in all_subjects
    assert subject_beta in all_subjects
    assert out_of_window_subject not in all_subjects

    # ---- repo_codex 投影含真实关键问题、不含注入消息 ----
    key_questions = [
        q for entry in data["repo_codex"] for q in entry["key_questions"]
    ]
    assert key_questions == real_prompts

    # 成功写入后打印两个产出文件的绝对路径（Req 7.6 / 10.1）。
    out = capsys.readouterr().out
    assert str(md_file.resolve()) in out
    assert str(json_file.resolve()) in out


# --------------------------------------------------------------------------- #
# Req 7.5：非交互式 + 无 --yes → 跳过覆盖、保留原文件
# --------------------------------------------------------------------------- #
def test_non_interactive_skips_overwrite_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Req 7.5：已存在且非交互式且无 --yes → 跳过覆盖、保留原文件、退出码 0。"""
    cfg = _write_config(tmp_path)
    outdir = tmp_path / "out"
    _force_non_interactive(monkeypatch)

    # 第一次运行：生成 .md。
    assert summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK]) == 0

    md_file = outdir / f"{_WEEK}.md"
    sentinel = "SENTINEL_ORIGINAL_CONTENT_DO_NOT_OVERWRITE"
    md_file.write_text(sentinel, encoding="utf-8")

    # 第二次运行（非交互式、无 --yes）：应跳过覆盖。
    capsys.readouterr()  # 清空缓冲
    code = summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK])

    assert code == 0  # 仍成功退出
    assert md_file.read_text(encoding="utf-8") == sentinel  # 原文件保留未被覆盖

    captured = capsys.readouterr()
    assert "已跳过覆盖" in (captured.out + captured.err)


# --------------------------------------------------------------------------- #
# Req 7.4：--yes 强制覆盖
# --------------------------------------------------------------------------- #
def test_yes_flag_forces_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 7.4：已存在 + --yes → 强制覆盖原文件。"""
    cfg = _write_config(tmp_path)
    outdir = tmp_path / "out"
    _force_non_interactive(monkeypatch)

    assert summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK]) == 0

    md_file = outdir / f"{_WEEK}.md"
    sentinel = "SENTINEL_SHOULD_BE_REPLACED"
    md_file.write_text(sentinel, encoding="utf-8")

    code = summarize.main(
        ["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK, "--yes"]
    )

    assert code == 0
    new_text = md_file.read_text(encoding="utf-8")
    assert new_text != sentinel  # 已被覆盖
    assert _WEEK in new_text  # 写入的是真实周报


# --------------------------------------------------------------------------- #
# Req 7.3：交互式覆盖确认 — 应答 "y" → 覆盖
# --------------------------------------------------------------------------- #
def test_interactive_confirm_yes_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 7.3：已存在 + 交互式 + 用户应答 "y" → 覆盖原文件。"""
    cfg = _write_config(tmp_path)
    outdir = tmp_path / "out"

    # 第一次运行（非交互式即可）生成 .md。
    _force_non_interactive(monkeypatch)
    assert summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK]) == 0

    md_file = outdir / f"{_WEEK}.md"
    sentinel = "SENTINEL_INTERACTIVE_SHOULD_BE_REPLACED"
    md_file.write_text(sentinel, encoding="utf-8")

    # 第二次运行：交互式 tty，input() 返回 "y" → 应覆盖。
    _force_interactive(monkeypatch, "y")
    code = summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK])

    assert code == 0
    new_text = md_file.read_text(encoding="utf-8")
    assert new_text != sentinel  # 用户确认覆盖
    assert _WEEK in new_text  # 写入的是真实周报


# --------------------------------------------------------------------------- #
# Req 7.3：交互式覆盖确认 — 应答 "n" → 保留原文件
# --------------------------------------------------------------------------- #
def test_interactive_confirm_no_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Req 7.3：已存在 + 交互式 + 用户应答 "n" → 跳过覆盖、保留原文件、退出码 0。"""
    cfg = _write_config(tmp_path)
    outdir = tmp_path / "out"

    # 第一次运行（非交互式即可）生成 .md。
    _force_non_interactive(monkeypatch)
    assert summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK]) == 0

    md_file = outdir / f"{_WEEK}.md"
    sentinel = "SENTINEL_INTERACTIVE_KEEP_ME"
    md_file.write_text(sentinel, encoding="utf-8")

    # 第二次运行：交互式 tty，input() 返回 "n" → 应保留原文件。
    _force_interactive(monkeypatch, "n")
    capsys.readouterr()  # 清空缓冲
    code = summarize.main(["--config", cfg, "--output-dir", str(outdir), "--week", _WEEK])

    assert code == 0  # 仍成功退出
    assert md_file.read_text(encoding="utf-8") == sentinel  # 原文件被保留

    captured = capsys.readouterr()
    assert "已跳过覆盖" in (captured.out + captured.err)


# --------------------------------------------------------------------------- #
# Req 11.3：不可恢复错误 — 配置缺失
# --------------------------------------------------------------------------- #
def test_missing_config_returns_nonzero_and_prints_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Req 11.3：配置文件缺失 → 非零退出并打印错误原因。"""
    missing = tmp_path / "does-not-exist.toml"
    outdir = tmp_path / "out"

    code = summarize.main(
        ["--config", str(missing), "--output-dir", str(outdir), "--week", _WEEK]
    )

    assert code != 0
    err = capsys.readouterr().err
    assert "错误" in err


# --------------------------------------------------------------------------- #
# 参数错误：非法 --week 格式
# --------------------------------------------------------------------------- #
def test_malformed_week_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """非法 --week（如 "2026-22"，缺少 W）→ 非零退出。"""
    cfg = _write_config(tmp_path)
    outdir = tmp_path / "out"

    code = summarize.main(
        ["--config", cfg, "--output-dir", str(outdir), "--week", "2026-22"]
    )

    assert code != 0
    err = capsys.readouterr().err
    assert "错误" in err
