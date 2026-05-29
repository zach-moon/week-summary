"""Data_Exporter（``export.py``）— Req 10（**跨层数据契约**）。

职责：把 :class:`~weekly_summary.models.AggregatedReport` 序列化为
**Structured_Export JSON**（LOCAL tier 与 SERVER tier 之间唯一的数据契约），
写入 ``dev_log/data/<Report_Identifier>.json``，并支持反序列化（round-trip）。

设计依据：design.md「Components and Interfaces / Data_Exporter」与
「Data Models / Structured_Export JSON schema」。

隐私边界（第一性约束）
----------------------
能够跨越到 SERVER tier 的**只有摘要数据**。具体而言：

- ``repo_codex`` 仅含 **摘要化** 的 ``themes`` / ``key_questions`` 与 ``session_count``，
  **绝不**包含 :class:`CodexSession` 的 ``session_id``、``date`` 或原始 transcript
  结构。因此 ``from_dict`` **无法、也不应**重建原始的 ``repo_sessions`` 全貌——
  这是**有意为之**的隐私设计（Req 8.5、8.6）。
- 因此本模块把**规范的 round-trip 等价定义在 JSON 投影（projection）层面**：

      to_dict(from_dict(to_dict(report))) == to_dict(report)

  亦即「导出后的 JSON」才是可比较的规范形式。``from_dict`` 重建出的
  ``repo_sessions`` 是与 ``repo_codex`` 投影**一致**的摘要重建（而非原始会话），
  从而既不泄露原始对话，又使 round-trip 性质（Property 17 / Req 10.4）良定义且可测。
- 除 ``repo_sessions`` 这一处隐私驱动的非对称之外，其余所有契约字段
  （``report_identifier``、起止日期、``distribution``、``repo_commits``、
  ``numbers``、``llm_suggestions``）都在 :class:`AggregatedReport` 层面被**精确保留**。

对设计示例 schema 的最小增量澄清
--------------------------------
设计文档「Structured_Export JSON schema」的 ``repo_commits`` 示例仅列出
``repo_id`` 与 ``commits``。为使 :class:`RepoCommits` 的 round-trip **无损**
（``repo_path`` 不丢失），本实现按设计意图做了一处**纯增量**澄清：在
``repo_commits`` 的每个条目中追加 ``repo_path`` 字段。该改动向后兼容、不改变
其余字段，使得 ``RepoCommits(repo_id, repo_path, commits)`` 可被精确重建。

类似地，``repo_codex`` 以 :class:`CodexSession` 的 ``project_dir`` 作为分组键并直接
存入 ``repo_id`` 字段（而非 basename），以保证分组在 ``from_dict`` 后可被**唯一**
重建（避免不同 ``project_dir`` 因同名 basename 而被错误合并），从而让上面的
JSON 投影 round-trip 恒等成立。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .models import (
    AggregatedReport,
    CodexSession,
    Commit,
    ProjectDistribution,
    RepoCommits,
)

__all__ = [
    "SCHEMA_VERSION",
    "ExportFormatError",
    "to_dict",
    "from_dict",
    "export_json",
]

# 契约版本号；新增字段须递增此值，前端按版本兼容处理（design「契约约束」）。
SCHEMA_VERSION = 1


class ExportFormatError(Exception):
    """反序列化遇到损坏 / 缺字段 / 类型不符的 JSON 时抛出（Req 10.5）。

    错误消息为描述性文本，会指明出错的字段名与期望类型，便于定位问题。
    """


# --------------------------------------------------------------------------- #
# 序列化：AggregatedReport -> Structured_Export dict
# --------------------------------------------------------------------------- #
def to_dict(report: AggregatedReport) -> dict[str, Any]:
    """把 :class:`AggregatedReport` 序列化为 Structured_Export JSON 字典。

    产出严格遵循 design「Data Models / Structured_Export JSON schema」（含本模块
    文档说明的 ``repo_commits.repo_path`` 增量字段）。``repo_codex`` 仅含摘要化的
    ``themes`` / ``key_questions``，不含任何原始 transcript（隐私边界）。

    Args:
        report: 待序列化的聚合周报。

    Returns:
        可直接 ``json.dump`` 的字典，键序与 schema 一致。
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "report_identifier": report.report_identifier,
        "week_start": report.week_start.isoformat(),
        "week_end": report.week_end.isoformat(),
        "distribution": [
            {
                "project_dir": d.project_dir,
                "project_name": _basename(d.project_dir),  # 派生展示字段
                "commit_count": d.commit_count,
                "session_count": d.session_count,
            }
            for d in report.distribution
        ],
        "repo_commits": [
            {
                "repo_id": rc.repo_id,
                "repo_path": rc.repo_path,  # 增量字段：保证无损 round-trip
                "commits": [
                    {"date": c.date.isoformat(), "subject": c.subject}
                    for c in rc.commits
                ],
            }
            for rc in report.repo_commits
        ],
        "repo_codex": _codex_projection(report.repo_sessions),
        "numbers": {
            "total_commits": report.total_commits,
            "total_sessions": report.total_sessions,
            "total_user_prompts": report.total_user_prompts,
        },
        "llm_suggestions": report.llm_suggestions,
    }


def _basename(path: str) -> str:
    """返回路径 basename（去除尾部分隔符），供前端展示。"""
    return Path(path).name or path


def _codex_projection(sessions: list[CodexSession]) -> list[dict[str, Any]]:
    """把扁平的 :class:`CodexSession` 列表按 ``project_dir`` 聚合为 repo_codex 投影。

    分组键为 ``project_dir`` 并直接作为 ``repo_id`` 存储（保证可被 ``from_dict`` 唯一
    重建）。每组：

    - ``session_count`` = 该组会话数。
    - ``themes`` = ``[]``（主题关键词为后续 LLM/关键词提取任务的占位；当前确定性留空）。
    - ``key_questions`` = 组内所有会话 ``user_prompts`` 的顺序拼接（摘要化关键问题）。

    分组顺序按 ``project_dir`` 首次出现顺序，确保输出确定可复现。
    """
    order: list[str] = []
    grouped: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for session in sessions:
        key = session.project_dir
        if key not in grouped:
            order.append(key)
            grouped[key] = []
            counts[key] = 0
        grouped[key].extend(session.user_prompts)
        counts[key] += 1

    return [
        {
            "repo_id": key,
            "session_count": counts[key],
            "themes": [],
            "key_questions": list(grouped[key]),
        }
        for key in order
    ]


# --------------------------------------------------------------------------- #
# 反序列化：Structured_Export dict -> AggregatedReport
# --------------------------------------------------------------------------- #
def from_dict(data: Any) -> AggregatedReport:
    """从 Structured_Export 字典重建 :class:`AggregatedReport`。

    ``repo_commits`` / ``distribution`` / ``numbers`` / 起止日期 /
    ``llm_suggestions`` 被精确重建；``repo_sessions`` 按 ``repo_codex`` 投影做
    **摘要重建**（不还原原始对话，隐私边界），使得
    ``to_dict(from_dict(to_dict(r))) == to_dict(r)`` 恒成立。

    Args:
        data: 解析自 JSON 的对象（应为字典）。

    Returns:
        重建后的 :class:`AggregatedReport`。

    Raises:
        ExportFormatError: 当 ``data`` 缺少必需字段、字段类型不符或日期非法时，
            消息中指明出错字段与期望类型（Req 10.5）。
    """
    if not isinstance(data, dict):
        raise ExportFormatError(
            f"顶层结构必须是 JSON 对象（dict），实际为 {type(data).__name__}"
        )

    # schema_version：必须存在且为整数。
    _require_int(data, "schema_version")

    report_identifier = _require_str(data, "report_identifier")
    week_start = _require_date(data, "week_start")
    week_end = _require_date(data, "week_end")

    distribution = _parse_distribution(_require_list(data, "distribution"))
    repo_commits = _parse_repo_commits(_require_list(data, "repo_commits"))
    repo_sessions = _parse_repo_codex(
        _require_list(data, "repo_codex"), default_date=week_start
    )

    numbers = _require_dict(data, "numbers")
    total_commits = _require_int(numbers, "total_commits", context="numbers")
    total_sessions = _require_int(numbers, "total_sessions", context="numbers")
    total_user_prompts = _require_int(
        numbers, "total_user_prompts", context="numbers"
    )

    llm_suggestions = _optional_str(data, "llm_suggestions")

    return AggregatedReport(
        report_identifier=report_identifier,
        week_start=week_start,
        week_end=week_end,
        distribution=distribution,
        repo_commits=repo_commits,
        repo_sessions=repo_sessions,
        total_commits=total_commits,
        total_sessions=total_sessions,
        total_user_prompts=total_user_prompts,
        llm_suggestions=llm_suggestions,
    )


def _parse_distribution(items: list[Any]) -> list[ProjectDistribution]:
    """重建 distribution；``project_name`` 为派生字段，重建时忽略。"""
    result: list[ProjectDistribution] = []
    for index, item in enumerate(items):
        ctx = f"distribution[{index}]"
        if not isinstance(item, dict):
            raise ExportFormatError(f"{ctx} 必须是对象（dict）")
        result.append(
            ProjectDistribution(
                project_dir=_require_str(item, "project_dir", context=ctx),
                commit_count=_require_int(item, "commit_count", context=ctx),
                session_count=_require_int(item, "session_count", context=ctx),
            )
        )
    return result


def _parse_repo_commits(items: list[Any]) -> list[RepoCommits]:
    """重建 repo_commits；``Commit.repo_id`` 由所属分组的 ``repo_id`` 还原。"""
    result: list[RepoCommits] = []
    for index, item in enumerate(items):
        ctx = f"repo_commits[{index}]"
        if not isinstance(item, dict):
            raise ExportFormatError(f"{ctx} 必须是对象（dict）")
        repo_id = _require_str(item, "repo_id", context=ctx)
        repo_path = _require_str(item, "repo_path", context=ctx)
        raw_commits = _require_list(item, "commits", context=ctx)
        commits: list[Commit] = []
        for c_index, raw in enumerate(raw_commits):
            c_ctx = f"{ctx}.commits[{c_index}]"
            if not isinstance(raw, dict):
                raise ExportFormatError(f"{c_ctx} 必须是对象（dict）")
            commits.append(
                Commit(
                    repo_id=repo_id,
                    date=_require_date(raw, "date", context=c_ctx),
                    subject=_require_str(raw, "subject", context=c_ctx),
                )
            )
        result.append(
            RepoCommits(repo_id=repo_id, repo_path=repo_path, commits=commits)
        )
    return result


def _parse_repo_codex(
    items: list[Any], *, default_date: date
) -> list[CodexSession]:
    """按 repo_codex 投影摘要重建 :class:`CodexSession` 列表。

    对每个分组（``repo_id`` = ``project_dir``，``session_count`` = N，
    ``key_questions`` = Q）重建 N 个会话：首个会话承载全部 ``key_questions``，
    其余为空。这样 :func:`to_dict` 再次序列化时可得到完全一致的 ``repo_codex``
    投影（``session_count`` 与 ``key_questions`` 均还原），保证 round-trip 恒等。
    原始 ``session_id`` / ``date`` 不在契约内，使用确定性占位值。
    """
    result: list[CodexSession] = []
    for index, item in enumerate(items):
        ctx = f"repo_codex[{index}]"
        if not isinstance(item, dict):
            raise ExportFormatError(f"{ctx} 必须是对象（dict）")
        repo_id = _require_str(item, "repo_id", context=ctx)
        session_count = _require_int(item, "session_count", context=ctx)
        # themes 必须存在且为列表（契约字段），当前重建不依赖其内容。
        _require_list(item, "themes", context=ctx)
        key_questions = _require_str_list(item, "key_questions", context=ctx)

        if session_count < 0:
            raise ExportFormatError(f"{ctx}.session_count 不能为负数")

        for i in range(session_count):
            prompts = list(key_questions) if i == 0 else []
            result.append(
                CodexSession(
                    session_id=f"{repo_id}#{i}",
                    project_dir=repo_id,
                    date=default_date,
                    user_prompts=prompts,
                    prompt_count=len(prompts),
                )
            )
    return result


# --------------------------------------------------------------------------- #
# 落盘：export_json
# --------------------------------------------------------------------------- #
def export_json(report: AggregatedReport, output_dir: Path) -> Path:
    """把 ``report`` 序列化并写入 ``<output_dir>/data/<Report_Identifier>.json``。

    ``<output_dir>/data/`` 目录不存在时创建（Req 10.2）。

    Args:
        report: 待导出的聚合周报。
        output_dir: 输出根目录（对应配置 ``output_dir``，默认 ``dev_log``）。

    Returns:
        实际写入的 JSON 文件绝对/相对路径（Req 10.1）。
    """
    data_dir = Path(output_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / f"{report.report_identifier}.json"
    target.write_text(
        json.dumps(to_dict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


# --------------------------------------------------------------------------- #
# 校验辅助（产出描述性 ExportFormatError，Req 10.5）
# --------------------------------------------------------------------------- #
def _field_label(key: str, context: str | None) -> str:
    return f"{context}.{key}" if context else key


def _require_present(data: dict[str, Any], key: str, context: str | None) -> Any:
    if key not in data:
        raise ExportFormatError(f"缺少必需字段 '{_field_label(key, context)}'")
    return data[key]


def _require_str(data: dict[str, Any], key: str, *, context: str | None = None) -> str:
    value = _require_present(data, key, context)
    if not isinstance(value, str):
        raise ExportFormatError(
            f"字段 '{_field_label(key, context)}' 期望为字符串（str），"
            f"实际为 {type(value).__name__}"
        )
    return value


def _require_int(data: dict[str, Any], key: str, *, context: str | None = None) -> int:
    value = _require_present(data, key, context)
    # bool 是 int 的子类，但语义上不接受布尔值作为计数 / 版本号。
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExportFormatError(
            f"字段 '{_field_label(key, context)}' 期望为整数（int），"
            f"实际为 {type(value).__name__}"
        )
    return value


def _require_list(data: dict[str, Any], key: str, *, context: str | None = None) -> list[Any]:
    value = _require_present(data, key, context)
    if not isinstance(value, list):
        raise ExportFormatError(
            f"字段 '{_field_label(key, context)}' 期望为数组（list），"
            f"实际为 {type(value).__name__}"
        )
    return value


def _require_dict(data: dict[str, Any], key: str, *, context: str | None = None) -> dict[str, Any]:
    value = _require_present(data, key, context)
    if not isinstance(value, dict):
        raise ExportFormatError(
            f"字段 '{_field_label(key, context)}' 期望为对象（dict），"
            f"实际为 {type(value).__name__}"
        )
    return value


def _require_str_list(
    data: dict[str, Any], key: str, *, context: str | None = None
) -> list[str]:
    value = _require_list(data, key, context=context)
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ExportFormatError(
                f"字段 '{_field_label(key, context)}[{i}]' 期望为字符串（str），"
                f"实际为 {type(item).__name__}"
            )
    return value


def _require_date(data: dict[str, Any], key: str, *, context: str | None = None) -> date:
    value = _require_str(data, key, context=context)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ExportFormatError(
            f"字段 '{_field_label(key, context)}' 不是合法的 ISO 日期"
            f"（YYYY-MM-DD）：{value!r}"
        ) from exc


def _optional_str(data: dict[str, Any], key: str, *, context: str | None = None) -> str | None:
    value = _require_present(data, key, context)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExportFormatError(
            f"字段 '{_field_label(key, context)}' 期望为字符串（str）或 null，"
            f"实际为 {type(value).__name__}"
        )
    return value
