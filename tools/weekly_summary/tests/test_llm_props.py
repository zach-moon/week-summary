"""LLM_Narrator 属性测试（Task 13.2 / Property 14）。

遵循「one property per file」约定，本文件**仅**实现 Property 14：

- **Property 14**（Req 8.1、8.4）：LLM 关闭时，全流程**零外发**——被注入的网络出口
  记录到零次调用。

（Property 16「LLM 开启时仅外发摘要且不含原始对话」见 ``test_llm_boundary_props.py``。）

实现手段：向 :func:`weekly_summary.llm.narrate` 注入一个**记录型 client**
（:class:`_RecordingClient`），它把每次收到的 :class:`~weekly_summary.llm.LLMRequest`
原样记录下来并返回固定文本，从而可在关闭时断言零次调用。
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given

from weekly_summary.llm import LLMInput, LLMRequest, narrate
from weekly_summary.models import LLMConfig


# --------------------------------------------------------------------------- #
# 记录型网络出口（可注入 client）：拦截并记录每次 LLMRequest，不触网。
# --------------------------------------------------------------------------- #
class _RecordingClient:
    """记录每次出网负载的可注入 :class:`~weekly_summary.llm.LLMClient`。"""

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def __call__(self, request: LLMRequest) -> str:
        self.requests.append(request)
        return "FAKE_LLM_OUTPUT"


# --------------------------------------------------------------------------- #
# Property 14：LLM 关闭时零外发
# --------------------------------------------------------------------------- #
_llm_inputs = st.builds(
    LLMInput,
    project_names=st.lists(st.text(max_size=12), max_size=5),
    topic_keywords=st.lists(st.text(max_size=12), max_size=5),
    commit_subjects=st.lists(st.text(max_size=24), max_size=5),
)


@given(
    llm_input=_llm_inputs,
    api_key=st.one_of(st.none(), st.text(max_size=20)),
)
def test_property_14_llm_disabled_zero_outbound(
    llm_input: LLMInput, api_key: str | None
) -> None:
    # Feature: weekly-dev-report, Property 14: LLM 关闭时全流程零外发
    """**Validates: Requirements 8.1, 8.4**

    当 ``llm.enabled == False`` 时，``narrate`` 在触达网络出口之前即返回 ``None``，
    被注入的记录型 client 记录到零次调用——无论是否提供 api_key。
    """
    recorder = _RecordingClient()

    result = narrate(llm_input, LLMConfig(enabled=False), api_key, client=recorder)

    assert result is None
    assert recorder.requests == []  # 零外发
