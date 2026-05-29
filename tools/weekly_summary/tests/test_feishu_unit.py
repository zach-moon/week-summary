"""Feishu_Integration 单元测试（Task 12.2，Req 14.1、14.2、14.3、14.4）。

覆盖飞书推送的四类行为，全部通过注入 ``sender`` 接缝在不触网的前提下验证：

- **Req 14.4（关闭零请求）**：``maybe_push`` 在 ``cfg.enabled == False`` 时返回
  ``None``，且被注入的 sender 从不被调用。
- **Req 14.1（开启推送一次）**：``push_to_feishu`` 成功时返回 ``ok=True``，sender
  恰好被调用一次，且收到的是飞书文本消息 payload；``maybe_push`` 在 ``enabled``
  时同样委托推送一次。
- **Req 14.2、14.3（解耦/三态）**：sender 抛网络/HTTP 异常时，``push_to_feishu`` /
  ``maybe_push`` 返回 ``ok=False`` 的 :class:`PushResult` 而**不抛异常**；结合关闭
  态共同覆盖「成功 / 失败 / 关闭」三态下本地产出一致（不受推送影响）。
- ``resolve_webhook_url``：环境变量 ``WEEKLY_SUMMARY_FEISHU_WEBHOOK`` 优先于配置值。
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from weekly_summary.feishu import (
    FEISHU_WEBHOOK_ENV,
    build_payload,
    maybe_push,
    push_to_feishu,
    resolve_webhook_url,
)
from weekly_summary.models import FeishuConfig

_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/abc123"
_MARKDOWN = "# 开发周报 2026-W22\n\n本周做了很多事。"


class _RecordingSender:
    """记录每次推送 (url, payload) 的可注入 sender；可选地模拟失败。"""

    def __init__(self, *, raises: BaseException | None = None) -> None:
        self.calls: list[tuple[str, bytes]] = []
        self._raises = raises

    def __call__(self, url: str, payload: bytes) -> None:
        self.calls.append((url, payload))
        if self._raises is not None:
            raise self._raises


def test_maybe_push_disabled_makes_zero_requests() -> None:
    """Req 14.4：关闭时返回 None 且 sender 从不被调用（零请求）。"""
    sender = _RecordingSender()
    cfg = FeishuConfig(enabled=False, webhook_url=_WEBHOOK)

    result = maybe_push(_MARKDOWN, cfg, sender=sender)

    assert result is None
    assert sender.calls == []  # 零请求


def test_push_to_feishu_success_calls_sender_once_with_text_payload() -> None:
    """Req 14.1：推送成功返回 ok=True，sender 恰好一次，payload 为飞书文本消息。"""
    sender = _RecordingSender()

    result = push_to_feishu(_MARKDOWN, _WEBHOOK, sender=sender)

    assert result.ok is True
    assert len(sender.calls) == 1  # 恰好推送一次

    url, payload = sender.calls[0]
    assert url == _WEBHOOK
    # payload 为飞书自定义机器人文本消息 JSON，正文即周报 Markdown。
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded == build_payload(_MARKDOWN)
    assert decoded["msg_type"] == "text"
    assert decoded["content"]["text"] == _MARKDOWN


def test_push_to_feishu_http_error_returns_failure_without_raising() -> None:
    """Req 14.2/14.3：HTTP 错误被捕获 → 返回 ok=False，不抛异常（与本地产出解耦）。"""
    http_error = urllib.error.HTTPError(
        url=_WEBHOOK, code=500, msg="Internal Server Error", hdrs=None, fp=None
    )
    sender = _RecordingSender(raises=http_error)

    result = push_to_feishu(_MARKDOWN, _WEBHOOK, sender=sender)

    assert result.ok is False
    assert result.message  # 含失败原因
    assert len(sender.calls) == 1


def test_push_to_feishu_network_error_returns_failure_without_raising() -> None:
    """Req 14.2/14.3：网络错误（URLError）被捕获 → 返回 ok=False，不抛异常。"""
    url_error = urllib.error.URLError("Connection refused")
    sender = _RecordingSender(raises=url_error)

    result = push_to_feishu(_MARKDOWN, _WEBHOOK, sender=sender)

    assert result.ok is False
    assert result.message


def test_maybe_push_enabled_pushes_once_with_text_payload() -> None:
    """Req 14.1：开启时 maybe_push 委托推送一次，返回 ok=True 且 payload 为文本消息。"""
    sender = _RecordingSender()
    cfg = FeishuConfig(enabled=True, webhook_url=_WEBHOOK)

    result = maybe_push(_MARKDOWN, cfg, sender=sender)

    assert result is not None
    assert result.ok is True
    assert len(sender.calls) == 1  # 恰好推送一次

    url, payload = sender.calls[0]
    assert url == _WEBHOOK
    assert json.loads(payload.decode("utf-8")) == build_payload(_MARKDOWN)


def test_maybe_push_enabled_failure_returns_result_without_raising() -> None:
    """Req 14.2/14.3：开启但推送失败时 maybe_push 返回 ok=False 的结果，不抛异常。

    与 ``test_maybe_push_disabled_makes_zero_requests`` 一起覆盖「成功/失败/关闭」
    三态：三种情况下编排层都只拿到返回值（None 或 PushResult），本地 .md/.json
    产出不受任何影响（无异常向编排层传播）。
    """
    sender = _RecordingSender(raises=urllib.error.URLError("Connection refused"))
    cfg = FeishuConfig(enabled=True, webhook_url=_WEBHOOK)

    result = maybe_push(_MARKDOWN, cfg, sender=sender)

    assert result is not None
    assert result.ok is False
    assert result.message  # 含失败原因
    assert len(sender.calls) == 1


def test_resolve_webhook_url_env_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_webhook_url：环境变量优先于配置值。"""
    env_url = "https://open.feishu.cn/open-apis/bot/v2/hook/from-env"
    monkeypatch.setenv(FEISHU_WEBHOOK_ENV, env_url)

    assert resolve_webhook_url("https://config.example/hook") == env_url


def test_resolve_webhook_url_falls_back_to_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_webhook_url：环境变量未设置时回退到配置值。"""
    monkeypatch.delenv(FEISHU_WEBHOOK_ENV, raising=False)

    assert resolve_webhook_url(_WEBHOOK) == _WEBHOOK
