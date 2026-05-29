"""Config_Loader 属性测试（Task 2.3 / Property 1）。

本文件实现配置解析相关的 Correctness Property：

- **Property 1**（Req 1.2）：对任意合法 TOML 配置（随机仓库列表 + 任意可选字段
  组合），``load_config`` 解析出的 :class:`~weekly_summary.models.Config` 各字段值
  应与输入内容一致。

> Property 15（LLM 配置持久性，Req 8.3）见独立文件 ``test_llm_config_persistence_props.py``。

实现手段：用 Hypothesis 生成字段值，**自行**把它们序列化为 TOML（带正确引号），
写入一个临时文件后调用 :func:`weekly_summary.config.load_config`，再与构造时记录的
期望 :class:`Config` 逐字段比对。

为避免与 ``@given`` 同用 pytest 函数级 fixture（如 ``tmp_path``）触发 Hypothesis
的 ``function_scoped_fixture`` 健康检查，文件 IO 一律用 :func:`tempfile.TemporaryDirectory`
在每个示例内部完成。

生成的字符串被限制在安全字符集（ASCII 字母 / 数字 / ``_`` / ``-`` / ``.`` / 空格），
不含引号、换行或反斜杠，从而无需任何 TOML 转义。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given

from weekly_summary.config import load_config
from weekly_summary.models import Config, FeishuConfig, LLMConfig

# 安全字符集：无需 TOML 转义（无引号 / 换行 / 反斜杠）。
_SAFE_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-. "
)
_safe_text = st.text(alphabet=_SAFE_ALPHABET, max_size=20)


def _q(value: str) -> str:
    """把安全字符串包成 TOML 基本字符串（无需转义）。"""
    return '"' + value + '"'


def _b(value: bool) -> str:
    """把布尔值序列化为 TOML 字面量。"""
    return "true" if value else "false"


@st.composite
def _config_case(draw: st.DrawFn) -> tuple[str, Config]:
    """生成一对 ``(toml_text, expected_config)``。

    顶层键值对全部先于 ``[llm]`` / ``[feishu]`` 表头输出，符合 TOML 语法；
    可选字段随机包含或省略——省略时期望值取 :class:`Config` 的设计默认值。
    """
    repos = draw(st.lists(_safe_text, max_size=5))
    lines = ["repos = [" + ", ".join(_q(repo) for repo in repos) + "]"]

    # output_dir（Req 1.5）：省略 → 默认 "dev_log"。
    if draw(st.booleans()):
        output_dir = draw(_safe_text)
        lines.append("output_dir = " + _q(output_dir))
    else:
        output_dir = "dev_log"

    # author（Req 2.4）：省略 → None。
    if draw(st.booleans()):
        author: str | None = draw(_safe_text)
        lines.append("author = " + _q(author))
    else:
        author = None

    # export_enabled（Req 10）：省略 → 默认 True。
    if draw(st.booleans()):
        export_enabled = draw(st.booleans())
        lines.append("export_enabled = " + _b(export_enabled))
    else:
        export_enabled = True

    # push_target：省略 → None。
    if draw(st.booleans()):
        push_target: str | None = draw(_safe_text)
        lines.append("push_target = " + _q(push_target))
    else:
        push_target = None

    # [llm] 表：省略 → LLMConfig 默认实例。
    if draw(st.booleans()):
        llm = LLMConfig(
            enabled=draw(st.booleans()),
            provider=draw(_safe_text),
            model=draw(_safe_text),
        )
        lines.append("[llm]")
        lines.append("enabled = " + _b(llm.enabled))
        lines.append("provider = " + _q(llm.provider))
        lines.append("model = " + _q(llm.model))
    else:
        llm = LLMConfig()

    # [feishu] 表：省略 → FeishuConfig 默认实例。
    if draw(st.booleans()):
        feishu = FeishuConfig(
            enabled=draw(st.booleans()),
            webhook_url=draw(_safe_text),
        )
        lines.append("[feishu]")
        lines.append("enabled = " + _b(feishu.enabled))
        lines.append("webhook_url = " + _q(feishu.webhook_url))
    else:
        feishu = FeishuConfig()

    expected = Config(
        repos=repos,
        output_dir=output_dir,
        author=author,
        export_enabled=export_enabled,
        push_target=push_target,
        llm=llm,
        feishu=feishu,
    )
    return "\n".join(lines) + "\n", expected


@given(case=_config_case())
def test_property_1_config_parse_correctness(case: tuple[str, Config]) -> None:
    # Feature: weekly-dev-report, Property 1: 配置解析正确性
    """**Validates: Requirements 1.2**

    把生成的合法 TOML 写入临时文件后 ``load_config`` 解析，得到的 :class:`Config`
    各字段值（repos、output_dir、author、export_enabled、push_target 及
    llm/feishu 的 enabled/provider/model/webhook_url）应与输入完全一致。
    """
    toml_text, expected = case
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / "weekly-summary.toml"
        config_path.write_text(toml_text, encoding="utf-8")
        loaded = load_config(config_path)

    assert loaded == expected
