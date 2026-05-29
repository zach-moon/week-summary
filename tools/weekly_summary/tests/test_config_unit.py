"""Config_Loader 单元测试（Task 2.5，Req 1.1、1.3、1.4、1.5、1.6、8.2）。

聚焦具体示例与边界，避免与 Property 1/15 重复：

- **Req 1.1（默认路径）**：``DEFAULT_CONFIG_PATH`` 指向 ``~/.config/weekly-summary.toml``
  （用 :data:`Path.home` 拼接断言，不读真实 home）。
- **Req 1.5（output_dir）**：配置提供 ``output_dir`` 时被如实采用。
- **Req 1.4（非法 TOML）**：语法错误 → :class:`ConfigParseError`，消息含出错位置
  （行号/列号/键名）。
- **Req 1.3（文件缺失）**：缺失 → :class:`ConfigMissingError`，消息含期望的绝对路径。
- **Req 1.6 / 8.2（默认模板）**：随包模板可被解析，且 ``llm.enabled == False``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weekly_summary.config import (
    DEFAULT_CONFIG_PATH,
    ConfigMissingError,
    ConfigParseError,
    load_config,
)

# 随包模板路径：tools/weekly_summary/templates/weekly-summary.toml
_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "templates" / "weekly-summary.toml"
)


def test_default_config_path_points_to_user_config_home() -> None:
    """Req 1.1：默认配置路径为 ``~/.config/weekly-summary.toml``。"""
    assert DEFAULT_CONFIG_PATH == Path.home() / ".config" / "weekly-summary.toml"


def test_output_dir_is_honored_when_provided(tmp_path: Path) -> None:
    """Req 1.5：配置提供 output_dir 时，解析结果如实采用该值。"""
    config_path = tmp_path / "weekly-summary.toml"
    config_path.write_text(
        'repos = []\noutput_dir = "custom_reports"\n', encoding="utf-8"
    )

    config = load_config(config_path)

    assert config.output_dir == "custom_reports"


def test_invalid_toml_raises_parse_error_with_location(tmp_path: Path) -> None:
    """Req 1.4：非法 TOML → ConfigParseError，消息含行号/列号或键名信息。"""
    config_path = tmp_path / "weekly-summary.toml"
    # 未闭合的数组：tomllib 报告 "(at line N, column M)"。
    config_path.write_text("repos = [oops\n", encoding="utf-8")

    with pytest.raises(ConfigParseError) as exc_info:
        load_config(config_path)

    message = str(exc_info.value)
    # 消息应携带可定位信息（行/列/键名）。
    assert "line" in message or "column" in message or "repos" in message


def test_missing_file_raises_missing_error_with_absolute_path(tmp_path: Path) -> None:
    """Req 1.3：文件缺失 → ConfigMissingError，消息含期望的绝对路径。"""
    missing = tmp_path / "nonexistent" / "weekly-summary.toml"

    with pytest.raises(ConfigMissingError) as exc_info:
        load_config(missing)

    message = str(exc_info.value)
    assert str(missing.resolve()) in message


def test_shipped_template_parses_with_llm_disabled() -> None:
    """Req 1.6 / 8.2：随包模板可被解析，且 LLM 开关默认关闭。"""
    assert _TEMPLATE_PATH.is_file()

    config = load_config(_TEMPLATE_PATH)

    assert config.llm.enabled is False
    # 模板亦应包含仓库列表与输出目录字段（Req 1.6 模板内容约定）。
    assert isinstance(config.repos, list)
    assert config.output_dir == "dev_log"
