"""Config_Loader — 读取并解析 ``~/.config/weekly-summary.toml``（Req 1）。

职责：从固定路径（或显式指定路径）读取 TOML 配置文件，解析为强类型的
:class:`~weekly_summary.models.Config` 对象。

错误语义（见设计「Error Handling」表）：
- 文件缺失 → 抛 :class:`ConfigMissingError`，消息含期望的配置文件**绝对路径**（Req 1.3）。
- TOML 语法非法 → 抛 :class:`ConfigParseError`，消息含出错位置（行号/键名，Req 1.4）。

实现说明：使用 Python 3.11 标准库 ``tomllib`` 解析 TOML，不引入第三方依赖。
本模块只负责加载与解析；采集 / 聚合 / 渲染等逻辑属于其它模块。
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from weekly_summary.models import Config, FeishuConfig, LLMConfig

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "ConfigError",
    "ConfigMissingError",
    "ConfigParseError",
    "load_config",
]

# 未显式指定路径时的默认配置文件位置（Req 1.1）。
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "weekly-summary.toml"


class ConfigError(Exception):
    """Config_Loader 相关错误的基类。"""


class ConfigMissingError(ConfigError):
    """配置文件缺失（Req 1.3）。

    错误消息中包含期望的配置文件绝对路径，便于用户创建。
    """


class ConfigParseError(ConfigError):
    """配置文件存在但 TOML 语法非法（Req 1.4）。

    错误消息中包含底层解析器报告的出错位置（行号/列号/键名）。
    """


def load_config(path: Path | None = None) -> Config:
    """加载并解析配置文件，返回强类型 :class:`Config`。

    Args:
        path: 配置文件路径；为 ``None`` 时使用 :data:`DEFAULT_CONFIG_PATH`
            （``~/.config/weekly-summary.toml``，Req 1.1）。支持 ``~`` 展开与
            相对路径（相对路径会被解析为绝对路径用于错误提示）。

    Returns:
        解析后的 :class:`Config`，包含 ``repos``、``output_dir``、``author``、
        ``export_enabled``、``push_target`` 以及 ``llm`` / ``feishu`` 子配置（Req 1.2）。

    Raises:
        ConfigMissingError: 配置文件不存在（消息含期望绝对路径，Req 1.3）。
        ConfigParseError: TOML 语法非法（消息含行号/键名，Req 1.4）。
    """
    config_path = (Path(path) if path is not None else DEFAULT_CONFIG_PATH).expanduser()
    # 解析为绝对路径，确保错误信息中始终给出可定位的绝对路径（Req 1.3）。
    abs_path = config_path.resolve()

    if not config_path.is_file():
        raise ConfigMissingError(
            f"配置文件缺失：期望在 {abs_path} 找到 weekly-summary.toml，但该文件不存在。"
            f"请在该路径创建配置文件（可参考默认模板）。"
        )

    raw_text = config_path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as exc:
        # tomllib 的错误消息通常已包含 "(at line N, column M)" 之类的位置信息（Req 1.4）。
        raise ConfigParseError(
            f"配置文件 TOML 语法非法（{abs_path}）：{exc}"
        ) from exc

    return _build_config(data)


def _build_config(data: dict[str, Any]) -> Config:
    """把解析后的 TOML 字典装配为 :class:`Config`，应用默认值。

    顶层字段缺省时回退到 :class:`Config` 的设计默认值；``[llm]`` / ``[feishu]``
    段缺省时使用对应 dataclass 的默认实例。字段值忠实反映配置内容（Req 1.2）。
    """
    llm_raw = data.get("llm") or {}
    llm = LLMConfig(
        enabled=llm_raw.get("enabled", LLMConfig.enabled),
        provider=llm_raw.get("provider", LLMConfig.provider),
        model=llm_raw.get("model", LLMConfig.model),
    )

    feishu_raw = data.get("feishu") or {}
    feishu = FeishuConfig(
        enabled=feishu_raw.get("enabled", FeishuConfig.enabled),
        webhook_url=feishu_raw.get("webhook_url", FeishuConfig.webhook_url),
    )

    return Config(
        repos=data.get("repos", []),
        output_dir=data.get("output_dir", "dev_log"),  # Req 1.5
        author=data.get("author"),  # 省略 → None（不过滤，Req 2.4）
        export_enabled=data.get("export_enabled", True),
        push_target=data.get("push_target"),
        llm=llm,
        feishu=feishu,
    )
