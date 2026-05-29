"""summarize.py — 编排层 / CLI 入口（Req 11、7、4）。

职责：把 LOCAL tier 的各组件接线为一条端到端流水线，并管理命令行参数、周报文件
覆盖确认与进程退出码。

设计依据：design.md「Components and Interfaces / summarize.py（编排层 / CLI 入口）」
与「Error Handling」「数据交接（HANDOFF）」两节。

默认流程（无参数，Req 11.1）::

    load_config → current_week_window → collect_commits + collect_sessions
      → aggregate →（可选 narrate）→ render_markdown → 写 dev_log/<id>.md
      →（可选 export_json）→（可选 rsync 推送）→（可选 push_to_feishu）

退出码：成功 ``0``（Req 11.2）；不可恢复错误非零并打印原因（Req 11.3）。

数据交接（HANDOFF）
-------------------
当指定 ``--push`` 且配置含 ``push_target`` 时，在导出 JSON **之后**执行 rsync over
SSH，仅同步 ``<output_dir>/data/`` 到远端（默认同步机制，复用既有 SSH 密钥互信）::

    rsync -az --delete-after <output_dir>/data/ "<push_target>"

**rsync 推送失败的处理决策（非致命）**：本地周报 ``.md`` / ``.json`` 在推送**之前**
已经成功落盘，是本 CLI 的核心交付物。依据 design「可选功能失败不影响核心产出」原则，
数据交接（推送）属于产出之后的可选旁路步骤——与 Feishu 推送同属「不影响本地产出」的
范畴。因此 rsync 失败被视为**非致命**：把失败原因清晰打印到 stderr，但**不**改变本地
产出，进程仍以 ``0`` 退出（核心流程已成功）。这与 design 的 Error Handling 表一致——
该表把「不可恢复错误」限定为配置缺失 / TOML 非法 / 反序列化损坏等，并未将推送失败列入。

覆盖行为（Req 7.3、7.4、7.5、7.6）
---------------------------------
- 输出目录不存在则创建（Req 7.2）。
- 目标 ``.md`` 不存在 → 直接写（Req 7.4）。
- 已存在且 ``--yes`` → 强制覆盖，不提示。
- 已存在且**交互式**（``sys.stdin.isatty()``）且非 ``--yes`` → 展示确认提示，按响应
  决定（Req 7.3）。
- 已存在且**非交互式**且非 ``--yes`` → 跳过覆盖、保留原文件、打印「已跳过覆盖」（Req 7.5）。
- 成功写入后打印**绝对路径**（Req 7.6）。
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import subprocess
import sys
from pathlib import Path

# 既支持以包形式导入（``weekly_summary.summarize``，测试场景 pythonpath=["tools"]），
# 也支持作为脚本直接运行（``python3 tools/weekly_summary/summarize.py``，Req 11.1）。
# 作为脚本运行时没有包上下文（``__package__`` 为空），需把 ``tools/`` 加入 sys.path，
# 以便下方的绝对导入 ``weekly_summary.*`` 能够解析。
if __package__ in (None, ""):  # pragma: no cover - 仅脚本入口分支
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weekly_summary.aggregate import aggregate
from weekly_summary.collectors.codex_collector import collect_sessions
from weekly_summary.collectors.git_collector import collect_commits
from weekly_summary.config import ConfigError, load_config
from weekly_summary.export import ExportFormatError, export_json
from weekly_summary.feishu import maybe_push
from weekly_summary.llm import (
    MissingCredentialError,
    build_llm_input,
    narrate,
    read_api_key,
)
from weekly_summary.models import AggregatedReport, WeekWindow
from weekly_summary.render import render_markdown
from weekly_summary.week_window import current_week_window, week_window_for

__all__ = ["main"]

EXIT_SUCCESS = 0
EXIT_ERROR = 1

# ``--week`` 接受形如 ``2026-W22`` 的 Report_Identifier 格式（ISO 年 + ISO 周，周序号
# 1~2 位）。区分大小写不敏感的 ``W``。
_WEEK_RE = re.compile(r"^(\d{4})-W(\d{1,2})$", re.IGNORECASE)


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器（全部参数可选，对应 design 的 CLI 参数）。"""
    parser = argparse.ArgumentParser(
        prog="summarize",
        description="开发周报自动生成（Weekly_Summary_CLI）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="配置文件路径；省略时使用 ~/.config/weekly-summary.toml（Req 1.1）",
    )
    parser.add_argument(
        "--week",
        type=str,
        default=None,
        help="目标周（形如 2026-W22）；省略时默认为本周（Req 4.1/4.2）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="输出目录；覆盖配置中的 output_dir（默认 dev_log）",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="导出 JSON 后经 rsync over SSH 同步 dev_log/data/ 到 push_target",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="目标周报已存在时强制覆盖，不展示确认提示（非交互式强制覆盖）",
    )
    return parser


def _parse_week(week: str) -> tuple[int, int]:
    """把 ``--week`` 的 ``YYYY-Www`` 字符串解析为 ``(year, iso_week)``（Req 4.2）。

    Args:
        week: 形如 ``"2026-W22"`` 的目标周字符串。

    Returns:
        ``(year, iso_week)`` 二元组。

    Raises:
        ValueError: 格式非法或周序号超出 1~53 范围。
    """
    match = _WEEK_RE.match(week.strip())
    if match is None:
        raise ValueError(
            f"无效的 --week 取值 {week!r}：期望形如 2026-W22 的 YYYY-Www 格式。"
        )
    year = int(match.group(1))
    iso_week = int(match.group(2))
    if not 1 <= iso_week <= 53:
        raise ValueError(
            f"无效的 ISO 周序号 {iso_week}（来自 --week {week!r}）：应在 1~53 之间。"
        )
    return year, iso_week


def _resolve_window(week: str | None) -> WeekWindow:
    """根据 ``--week`` 选择时间窗：指定周或默认本周（Req 4.1、4.2）。"""
    if week:
        year, iso_week = _parse_week(week)
        return week_window_for(year, iso_week)
    return current_week_window()


def _emit_warnings(warnings: list, *, label: str) -> None:
    """把采集器产出的非致命警告打印到 stderr，并继续流程（Req 2.3、3.5、3.6）。"""
    for warning in warnings:
        print(f"[{label}] {warning.source}: {warning.message}", file=sys.stderr)


def _apply_llm(report: AggregatedReport, config) -> AggregatedReport:
    """在 LLM 开启时生成建议并并入报告；关闭 / 失败 / 缺凭证时安全降级。

    - 关闭（``config.llm.enabled is False``）：不构造外发数据、不发起请求，直接返回原
      报告（零外发，Req 8.1、8.4）。
    - 缺凭证：``narrate`` 抛 :class:`MissingCredentialError`，此处捕获并打印描述性提示，
      生成**不含** LLM 章节的周报（Req 9.3）。
    - 调用失败或被禁用：``narrate`` 返回 ``None`` → 不附加 LLM 章节（Req 9.2）。
    - 成功：``narrate`` 返回字符串 → 用 :func:`dataclasses.replace` 产出带 LLM 建议的
      新报告（``AggregatedReport`` 为 frozen dataclass，需 replace 而非原地赋值）。

    LLM 输出仅由 :func:`build_llm_input` 构造的**摘要要点**派生，绝不含原始对话
    （隐私边界，Req 8.5、8.6）。
    """
    if not config.llm.enabled:
        return report

    llm_input = build_llm_input(report)
    try:
        suggestions = narrate(llm_input, config.llm, read_api_key())
    except MissingCredentialError as exc:
        # Req 9.3：打印缺凭证的描述性信息，继续生成不含 LLM 章节的周报。
        print(str(exc), file=sys.stderr)
        return report

    if suggestions is None:
        # Req 9.2：调用失败（或被禁用）→ 无 LLM 章节，继续生成。
        return report

    return dataclasses.replace(report, llm_suggestions=suggestions)


def _write_markdown(
    markdown: str,
    output_dir: Path,
    report_identifier: str,
    *,
    force: bool,
) -> Path | None:
    """把渲染好的 Markdown 写入 ``<output_dir>/<id>.md`` 并处理覆盖逻辑（Req 7）。

    Args:
        markdown: 渲染好的周报文本。
        output_dir: 输出目录（不存在则创建，Req 7.2）。
        report_identifier: Report_Identifier，作为文件名主体（Req 7.1）。
        force: ``--yes``，已存在时强制覆盖、不提示。

    Returns:
        成功写入时返回写入文件的**绝对路径**；因用户拒绝或非交互式而跳过覆盖时返回
        ``None``。
    """
    output_dir.mkdir(parents=True, exist_ok=True)  # Req 7.2
    target = output_dir / f"{report_identifier}.md"  # Req 7.1
    abs_target = target.resolve()

    if target.exists() and not force:
        if sys.stdin.isatty():
            # 交互式：展示确认提示，按用户响应决定（Req 7.3）。
            answer = input(
                f"周报文件已存在：{abs_target}\n是否覆盖？[y/N] "
            ).strip().lower()
            if answer not in ("y", "yes"):
                print(f"已跳过覆盖，保留原文件：{abs_target}", file=sys.stderr)
                return None
        else:
            # 非交互式：跳过覆盖、保留原文件并提示（Req 7.5）。
            print(
                f"已跳过覆盖（非交互式环境，无法确认），保留原文件：{abs_target}",
                file=sys.stderr,
            )
            return None

    target.write_text(markdown, encoding="utf-8")
    # Req 7.6：成功写入后打印绝对路径。
    print(f"已写入周报：{abs_target}")
    return abs_target


def _push_data(output_dir: Path, push_target: str) -> None:
    """经 rsync over SSH 同步 ``<output_dir>/data/`` 到 ``push_target``（HANDOFF）。

    复用既有 SSH 密钥互信，无需额外密钥配置。失败被视为**非致命**：打印原因到
    stderr，不影响已落盘的本地产出，进程仍以成功退出（见模块文档的决策说明）。

    使用 :func:`subprocess.run` 以**参数列表**（非 shell 字符串）调用 rsync，
    ``push_target`` 作为单个参数传入，避免 shell 注入。
    """
    data_dir = output_dir / "data"
    if not data_dir.exists():
        # 通常因 export_enabled=false 而无数据可推；提示并跳过（非致命）。
        print(
            f"[push] 数据目录不存在，跳过 rsync 推送：{data_dir.resolve()}",
            file=sys.stderr,
        )
        return

    # 源路径加尾部分隔符 → rsync 同步目录内容（而非把 data 目录本身嵌套进去）。
    source = f"{data_dir}{os.sep}"
    cmd = ["rsync", "-az", "--delete-after", source, push_target]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        print(f"[push] rsync 执行失败（非致命，本地产出不受影响）：{exc}", file=sys.stderr)
        return

    if result.returncode != 0:
        detail = result.stderr.strip() or f"rsync 退出码 {result.returncode}"
        print(
            f"[push] rsync 同步失败（非致命，本地产出不受影响）：{detail}",
            file=sys.stderr,
        )
        return

    print(f"[push] 已同步 {source} → {push_target}")


def _push_feishu(markdown: str, config) -> None:
    """按配置可选地把周报推送到飞书；与本地产出完全解耦（Req 14）。

    关闭时 :func:`maybe_push` 返回 ``None`` 且不发起任何请求（Req 14.4）；开启时返回
    :class:`PushResult`，此处仅把结果记录到 stderr，绝不影响本地 ``.md`` / ``.json``
    产出（Req 14.2、14.3）。
    """
    result = maybe_push(markdown, config.feishu)
    if result is None:
        return  # 飞书集成关闭：零请求。
    if result.ok:
        print(f"[feishu] {result.message}", file=sys.stderr)
    else:
        print(f"[feishu] {result.message}", file=sys.stderr)


def main(argv: list[str]) -> int:
    """CLI 入口与端到端编排（Req 11）。

    Args:
        argv: 命令行参数（不含程序名），通常为 ``sys.argv[1:]``。

    Returns:
        进程退出码：成功 ``0``（Req 11.2）；不可恢复错误非零（Req 11.3）。
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        # 1) 加载配置（缺失 / 语法非法 → ConfigError，不可恢复，Req 1.3/1.4/11.3）。
        config_path = Path(args.config) if args.config else None
        config = load_config(config_path)

        # 2) 时间窗：指定周或默认本周（Req 4.1、4.2）。
        try:
            window = _resolve_window(args.week)
        except ValueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return EXIT_ERROR

        # 输出目录：命令行 --output-dir 覆盖配置 output_dir（默认 dev_log）。
        output_dir = Path(args.output_dir) if args.output_dir else Path(config.output_dir)

        # 3) 采集：git 提交 + codex 会话；警告打印到 stderr 但不中止（Req 2.3、3.5、3.6）。
        repo_commits, git_warnings = collect_commits(
            config.repos, window, config.author
        )
        _emit_warnings(git_warnings, label="git")
        sessions, codex_warnings = collect_sessions(window)
        _emit_warnings(codex_warnings, label="codex")

        # 4) 聚合。
        report = aggregate(config, window, repo_commits, sessions)

        # 5) 可选 LLM：在渲染之前并入建议，使渲染包含 LLM 章节（Req 9）。
        report = _apply_llm(report, config)

        # 6) 渲染 Markdown（在 LLM 之后，以包含可选建议章节）。
        markdown = render_markdown(report)

        # 7) 写入 dev_log/<id>.md，处理覆盖逻辑（Req 7.1~7.6）。
        _write_markdown(
            markdown,
            output_dir,
            report.report_identifier,
            force=args.yes,
        )

        # 8) 可选导出结构化 JSON（Req 10）。
        if config.export_enabled:
            json_path = export_json(report, output_dir)
            print(f"已导出结构化数据：{json_path.resolve()}")

        # 9) 可选数据交接：rsync over SSH（Req 设计 HANDOFF；失败非致命）。
        if args.push:
            if config.push_target:
                _push_data(output_dir, config.push_target)
            else:
                print(
                    "[push] 已指定 --push 但配置未提供 push_target，跳过 rsync 推送。",
                    file=sys.stderr,
                )

        # 10) 可选飞书推送（与本地产出解耦，Req 14）。
        _push_feishu(markdown, config)

        return EXIT_SUCCESS

    except (ConfigError, ExportFormatError) as exc:
        # 已知的不可恢复错误：打印描述性原因并非零退出（Req 11.3）。
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - 兜底：任何未预期的致命错误均非零退出
        print(f"错误：生成周报时发生不可恢复的错误：{exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
