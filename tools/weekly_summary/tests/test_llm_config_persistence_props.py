"""LLM 配置持久性属性测试（Task 2.4 / Property 15）。

本文件实现单条 Correctness Property：

- **Property 15**（Req 8.3）：对任意 ``llm.enabled`` 取值，加载配置（并在重复加载 /
  读取后）其 ``enabled`` 值不应被运行时修改或重置——开启保持开启，关闭保持关闭。

实现手段：用 Hypothesis 生成 ``llm.enabled`` 的布尔取值，将其序列化为一份最小合法
TOML 配置写入临时文件，再调用 :func:`weekly_summary.config.load_config`。为模拟「加载
并运行流程后」对配置的反复读取，连续加载多次并断言每次得到的 ``enabled`` 都与写入值
一致且彼此相等。

为避免 ``@given`` 与 pytest 函数级 fixture（如 ``tmp_path``）同用而触发 Hypothesis 的
``function_scoped_fixture`` 健康检查，文件 IO 一律用 :func:`tempfile.TemporaryDirectory`
在每个示例内部完成。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import hypothesis.strategies as st
from hypothesis import given

from weekly_summary.config import load_config


def _b(value: bool) -> str:
    """把布尔值序列化为 TOML 字面量。"""
    return "true" if value else "false"


@given(enabled=st.booleans())
def test_property_15_llm_config_persistence(enabled: bool) -> None:
    # Feature: weekly-dev-report, Property 15: LLM 配置持久性
    """**Validates: Requirements 8.3**

    对任意 ``llm.enabled`` 取值，加载同一份配置文件后其 ``enabled`` 值应忠实反映写入值；
    重复加载 / 读取（模拟「加载并运行流程后」对配置的反复消费）不会把它重置或修改
    （开启保持开启，关闭保持关闭）。
    """
    toml_text = f"repos = []\n[llm]\nenabled = {_b(enabled)}\n"
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / "weekly-summary.toml"
        config_path.write_text(toml_text, encoding="utf-8")

        # 连续多次加载 / 读取，模拟运行流程中对配置的反复消费。
        loads = [load_config(config_path) for _ in range(3)]

    # 每次加载得到的 enabled 都应等于写入值（不被重置或修改）。
    for cfg in loads:
        assert cfg.llm.enabled == enabled

    # 反复读取彼此一致（运行时不会漂移）。
    assert len({cfg.llm.enabled for cfg in loads}) == 1
