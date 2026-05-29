"""Data_Exporter 单元测试（Task 9.3，Req 10.1、10.2、10.5）。

聚焦具体示例与错误路径：

- :func:`export_json` 把 JSON 写入 ``<output_dir>/data/<Report_Identifier>.json``，
  目录不存在时创建 ``data/``（Req 10.1、10.2），并返回写入路径。
- :func:`from_dict` 对损坏 / 非法输入抛 :class:`ExportFormatError` 且消息具描述性
  （Req 10.5）：顶层非 dict、缺 ``report_identifier``、``numbers`` 计数类型错误、
  日期字符串非法等。

与属性测试（``test_export_props.py`` 的 round-trip）互补：此处不做 round-trip，只验证
落地行为与反序列化的错误语义。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from weekly_summary.export import (
    ExportFormatError,
    export_json,
    from_dict,
    to_dict,
)
from weekly_summary.models import (
    AggregatedReport,
    CodexSession,
    Commit,
    ProjectDistribution,
    RepoCommits,
)


def _sample_report() -> AggregatedReport:
    """一份含 commit / session / 分布的合法报告。"""
    return AggregatedReport(
        report_identifier="2026-W22",
        week_start=date(2026, 5, 25),
        week_end=date(2026, 5, 31),
        distribution=[
            ProjectDistribution(project_dir="/home/v/proj-a", commit_count=3, session_count=2),
            ProjectDistribution(project_dir="/home/v/proj-b", commit_count=0, session_count=0),
        ],
        repo_commits=[
            RepoCommits(
                repo_id="proj-a",
                repo_path="/home/v/proj-a",
                commits=[
                    Commit(repo_id="proj-a", date=date(2026, 5, 26), subject="add login route"),
                ],
            ),
        ],
        repo_sessions=[
            CodexSession(
                session_id="uuid-1",
                project_dir="/home/v/proj-a",
                date=date(2026, 5, 26),
                user_prompts=["如何保护路由？"],
                prompt_count=1,
            ),
        ],
        total_commits=3,
        total_sessions=2,
        total_user_prompts=5,
        llm_suggestions=None,
    )


def _valid_dict() -> dict:
    """一份可被 ``from_dict`` 成功解析的合法字典（用于逐项破坏）。"""
    return to_dict(_sample_report())


# --------------------------------------------------------------------------- #
# export_json：落地路径与目录创建（Req 10.1、10.2）
# --------------------------------------------------------------------------- #
def test_export_json_writes_to_data_subdir_and_returns_path(tmp_path: Path) -> None:
    """写入 ``<output_dir>/data/<id>.json`` 并返回该路径（Req 10.1）。"""
    report = _sample_report()
    output_dir = tmp_path / "dev_log"

    written = export_json(report, output_dir)

    expected = output_dir / "data" / "2026-W22.json"
    assert written == expected
    assert written.is_file()


def test_export_json_creates_missing_data_dir(tmp_path: Path) -> None:
    """``data/`` 不存在时创建后再写入（Req 10.2）。"""
    output_dir = tmp_path / "dev_log"
    assert not (output_dir / "data").exists()

    export_json(_sample_report(), output_dir)

    assert (output_dir / "data").is_dir()


def test_export_json_content_is_valid_roundtrippable_json(tmp_path: Path) -> None:
    """写出的文件是合法 JSON，且其内容等于 ``to_dict`` 的产物（Req 10.3）。"""
    report = _sample_report()
    written = export_json(report, tmp_path / "dev_log")

    loaded = json.loads(written.read_text(encoding="utf-8"))
    assert loaded == to_dict(report)
    assert loaded["report_identifier"] == "2026-W22"
    assert loaded["schema_version"] == 1


def test_export_json_nested_output_dir_created(tmp_path: Path) -> None:
    """多级不存在的 output_dir 也应被创建（mkdir parents）。"""
    output_dir = tmp_path / "a" / "b" / "dev_log"
    written = export_json(_sample_report(), output_dir)
    assert written.is_file()
    assert written.parent == output_dir / "data"


# --------------------------------------------------------------------------- #
# from_dict：描述性 ExportFormatError（Req 10.5）
# --------------------------------------------------------------------------- #
def test_from_dict_rejects_non_dict_top_level() -> None:
    """顶层非 dict（如列表）→ ExportFormatError，消息含类型说明。"""
    with pytest.raises(ExportFormatError) as exc:
        from_dict([1, 2, 3])
    assert "dict" in str(exc.value)


@pytest.mark.parametrize("bad", ["not a dict", 42, None, 3.14])
def test_from_dict_rejects_various_non_dict(bad: object) -> None:
    """多种非 dict 顶层输入均被拒绝。"""
    with pytest.raises(ExportFormatError):
        from_dict(bad)


def test_from_dict_missing_report_identifier() -> None:
    """缺 ``report_identifier`` → 描述性错误，消息含该字段名。"""
    data = _valid_dict()
    del data["report_identifier"]
    with pytest.raises(ExportFormatError) as exc:
        from_dict(data)
    assert "report_identifier" in str(exc.value)


def test_from_dict_wrong_typed_number() -> None:
    """``numbers.total_commits`` 类型错误（字符串）→ 描述性错误。"""
    data = _valid_dict()
    data["numbers"]["total_commits"] = "twelve"
    with pytest.raises(ExportFormatError) as exc:
        from_dict(data)
    message = str(exc.value)
    assert "total_commits" in message
    assert "整数" in message or "int" in message


def test_from_dict_bool_not_accepted_as_number() -> None:
    """布尔值不被当作整数计数（bool 是 int 子类，但语义上拒绝）。"""
    data = _valid_dict()
    data["numbers"]["total_sessions"] = True
    with pytest.raises(ExportFormatError) as exc:
        from_dict(data)
    assert "total_sessions" in str(exc.value)


def test_from_dict_bad_date_string() -> None:
    """``week_start`` 非法日期字符串 → 描述性错误，消息含字段名。"""
    data = _valid_dict()
    data["week_start"] = "2026-13-99"
    with pytest.raises(ExportFormatError) as exc:
        from_dict(data)
    message = str(exc.value)
    assert "week_start" in message
    assert "ISO" in message or "日期" in message


def test_from_dict_missing_numbers_section() -> None:
    """缺 ``numbers`` 段 → 描述性错误，消息含字段名。"""
    data = _valid_dict()
    del data["numbers"]
    with pytest.raises(ExportFormatError) as exc:
        from_dict(data)
    assert "numbers" in str(exc.value)


def test_from_dict_distribution_entry_not_object() -> None:
    """``distribution`` 中某条目非对象 → 描述性错误，定位到索引。"""
    data = _valid_dict()
    data["distribution"] = ["oops"]
    with pytest.raises(ExportFormatError) as exc:
        from_dict(data)
    assert "distribution[0]" in str(exc.value)


def test_from_dict_llm_suggestions_wrong_type() -> None:
    """``llm_suggestions`` 既非 str 也非 null（如整数）→ 描述性错误。"""
    data = _valid_dict()
    data["llm_suggestions"] = 123
    with pytest.raises(ExportFormatError) as exc:
        from_dict(data)
    assert "llm_suggestions" in str(exc.value)


def test_from_dict_valid_dict_succeeds() -> None:
    """合法字典应被成功解析（负向用例的对照基准）。"""
    report = from_dict(_valid_dict())
    assert report.report_identifier == "2026-W22"
    assert report.total_commits == 3
    assert report.week_start == date(2026, 5, 25)
