"""LLM_Narrator 单元测试（Task 11.3，Req 9.2、9.3）。

覆盖两条降级 / 错误语义：

- **Req 9.2（调用失败降级）**：LLM 开启且有凭证，但 client 调用抛异常时，
  :func:`weekly_summary.llm.narrate` 捕获异常并返回 ``None``（不向上层抛出），
  以便编排层继续生成不含 LLM 章节的周报。
- **Req 9.3（缺凭证）**：LLM 开启但既未显式传入 api_key、环境变量
  ``WEEKLY_SUMMARY_LLM_API_KEY`` 也未设置时，:func:`narrate` 抛
  :class:`~weekly_summary.llm.MissingCredentialError`（描述性错误），供编排层
  打印缺凭证提示并生成不含 LLM 章节的周报。
"""

from __future__ import annotations

import pytest

from weekly_summary.llm import (
    API_KEY_ENV_VAR,
    LLMInput,
    MissingCredentialError,
    narrate,
)
from weekly_summary.models import LLMConfig

_SAMPLE_INPUT = LLMInput(
    project_names=["proj-a"],
    topic_keywords=["proj-a", "repo-a"],
    commit_subjects=["修复登录 bug", "add tests"],
)


def test_narrate_returns_none_when_client_raises() -> None:
    """Req 9.2：开启且有凭证，但 client 调用失败 → 返回 None（静默降级）。"""

    def _failing_client(_request):
        raise RuntimeError("模拟网络/HTTP 调用失败")

    result = narrate(
        _SAMPLE_INPUT,
        LLMConfig(enabled=True),
        "test-api-key",
        client=_failing_client,
    )

    assert result is None


def test_narrate_raises_missing_credential_when_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 9.3：开启但缺凭证（入参 None + 环境变量未设置）→ 抛 MissingCredentialError。"""
    # 清除环境变量，确保唯一凭证来源为空。
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)

    recorded: list[object] = []

    def _recording_client(request):
        recorded.append(request)
        return "should-not-be-called"

    with pytest.raises(MissingCredentialError) as exc_info:
        narrate(
            _SAMPLE_INPUT,
            LLMConfig(enabled=True),
            None,
            client=_recording_client,
        )

    # 描述性错误信息应提示缺失的环境变量名（供编排层打印）。
    assert API_KEY_ENV_VAR in str(exc_info.value)
    # 缺凭证时不应触达网络出口（零外发）。
    assert recorded == []
