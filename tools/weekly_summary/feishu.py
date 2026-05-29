"""Feishu_Integration（``feishu.py``）— Req 14（可选）。

职责：在飞书集成被**显式开启**时，于周报生成完成后向自定义机器人
（custom bot）的 incoming webhook 做一次**单向推送**（CLI → 飞书），推送内容为
周报 Markdown 文本（Req 14.1）。

第一性约束 —— 与本地产出完全解耦
--------------------------------
本模块对 ``dev_log/<id>.md`` 与 ``dev_log/data/<id>.json`` 的生成**零影响**：

- 推送结果以返回值（:class:`PushResult`）表达成功 / 失败，**绝不**通过抛异常
  把网络错误传播给编排层（Req 14.2、14.3）。任何 HTTP / 网络 / 编码错误都会被
  捕获并记入 :attr:`PushResult.message`。
- 关闭状态下不发起**任何**网络请求：编排层应仅在开启时调用
  :func:`push_to_feishu`；本模块另提供便捷封装 :func:`maybe_push`，当
  ``cfg.enabled`` 为 ``False`` 时直接返回 ``None`` 且不触碰网络（Req 14.4）。

机密处理
--------
webhook URL 视为机密。:func:`resolve_webhook_url` 让环境变量
``WEEKLY_SUMMARY_FEISHU_WEBHOOK`` **优先于**配置 / 传入值，便于把密钥经环境注入
而不写入仓库内的 TOML。

依赖
----
仅用标准库 :mod:`urllib`（无第三方依赖）。实际网络调用被抽象到一个可注入的
``sender`` 接缝（seam）后面，便于测试在不触网的情况下替换实现。

飞书 payload 格式
-----------------
采用自定义机器人 incoming webhook 的标准文本消息 JSON::

    {"msg_type": "text", "content": {"text": <报告文本>}}

消息正文即周报 Markdown 文本。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .models import FeishuConfig

__all__ = [
    "FEISHU_WEBHOOK_ENV",
    "PushResult",
    "Sender",
    "resolve_webhook_url",
    "build_payload",
    "push_to_feishu",
    "maybe_push",
]

# 环境变量名：优先于配置 / 传入值提供 webhook URL（视为机密，Req 14）。
FEISHU_WEBHOOK_ENV = "WEEKLY_SUMMARY_FEISHU_WEBHOOK"

# 默认网络超时（秒）。推送是「尽力而为」的旁路，避免长时间阻塞本地流程。
_DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True)
class PushResult:
    """一次飞书推送的结果（不可变值对象）。

    通过返回值而非异常来表达成败，使调用方无需 ``try/except`` 即可判断结果，
    从而保证本地周报产出与推送**完全解耦**（Req 14.2、14.3）。

    Attributes:
        ok: 推送是否成功（HTTP 2xx 视为成功）。
        message: 人类可读的结果说明。成功时为简短确认信息；失败时为**失败原因**
            （如 HTTP 状态码、网络错误类型与描述），供调用方记录日志。
    """

    ok: bool
    message: str


# 可注入的网络接缝：接收 (url, payload_bytes) 并执行一次 POST。
# 默认实现为 :func:`_urllib_sender`；测试可传入替身以避免真实网络调用。
Sender = Callable[[str, bytes], None]


def resolve_webhook_url(config_value: str) -> str:
    """解析最终生效的 webhook URL，环境变量优先。

    优先级：环境变量 ``WEEKLY_SUMMARY_FEISHU_WEBHOOK`` > ``config_value``。
    这样可以把机密经环境注入，而不必写进仓库内的 ``weekly-summary.toml``。

    Args:
        config_value: 来自配置 / 调用方的 webhook URL（可能为空字符串）。

    Returns:
        生效的 webhook URL。环境变量存在且非空白时返回其值（两端空白会被
        去除）；否则原样返回 ``config_value``。
    """
    env_value = os.environ.get(FEISHU_WEBHOOK_ENV)
    if env_value is not None and env_value.strip():
        return env_value.strip()
    return config_value


def build_payload(markdown: str) -> dict:
    """构造飞书自定义机器人文本消息 payload。

    Args:
        markdown: 周报 Markdown 文本，作为消息正文。

    Returns:
        形如 ``{"msg_type": "text", "content": {"text": markdown}}`` 的字典。
    """
    return {"msg_type": "text", "content": {"text": markdown}}


def _urllib_sender(url: str, payload: bytes) -> None:
    """默认 ``sender``：用标准库 :mod:`urllib` 发起一次 JSON POST。

    成功（HTTP 2xx）时正常返回；非 2xx 由 :class:`urllib.error.HTTPError`
    表达，网络层错误由 :class:`urllib.error.URLError` 表达，均由
    :func:`push_to_feishu` 统一捕获并转为 :class:`PushResult`。
    """
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_DEFAULT_TIMEOUT) as response:
        # 读取并丢弃响应体；状态码非 2xx 时 urlopen 已抛 HTTPError。
        response.read()


def push_to_feishu(
    markdown: str,
    webhook_url: str,
    *,
    sender: Sender | None = None,
) -> PushResult:
    """向飞书自定义机器人 incoming webhook 做**一次**单向推送（Req 14.1）。

    本函数保证**不抛异常**：任何编码 / 网络 / HTTP 错误都会被捕获并记录在
    返回的 :class:`PushResult` 中，从而不影响本地 ``.md`` / ``.json`` 产出
    （Req 14.2、14.3）。调用方应仅在飞书集成开启时调用本函数（关闭时零请求，
    见 :func:`maybe_push`，Req 14.4）。

    Args:
        markdown: 周报 Markdown 文本，作为推送的消息正文。
        webhook_url: 自定义机器人 incoming webhook URL。会先经
            :func:`resolve_webhook_url` 处理，使环境变量覆盖生效。
        sender: 可选的网络接缝。默认使用 :func:`_urllib_sender`（标准库
            urllib）。测试可注入替身以避免真实网络调用，并断言「恰好推送一次」。

    Returns:
        :class:`PushResult`：``ok=True`` 表示推送成功；``ok=False`` 时
        ``message`` 含失败原因。
    """
    url = resolve_webhook_url(webhook_url)
    if not url or not url.strip():
        return PushResult(ok=False, message="飞书推送失败：未配置 webhook URL")

    send = sender if sender is not None else _urllib_sender

    try:
        payload = json.dumps(build_payload(markdown), ensure_ascii=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:  # 极端情况下的序列化错误
        return PushResult(ok=False, message=f"飞书推送失败：payload 序列化错误：{exc}")

    try:
        send(url, payload)
    except urllib.error.HTTPError as exc:
        return PushResult(
            ok=False,
            message=f"飞书推送失败：HTTP {exc.code} {exc.reason}",
        )
    except urllib.error.URLError as exc:
        return PushResult(ok=False, message=f"飞书推送失败：网络错误：{exc.reason}")
    except Exception as exc:  # noqa: BLE001 — 兜底，确保绝不向编排层抛出
        return PushResult(
            ok=False,
            message=f"飞书推送失败：{type(exc).__name__}: {exc}",
        )

    return PushResult(ok=True, message="飞书推送成功")


def maybe_push(
    markdown: str,
    cfg: FeishuConfig,
    *,
    sender: Sender | None = None,
) -> PushResult | None:
    """按配置决定是否推送的便捷封装（编排层友好）。

    当 ``cfg.enabled`` 为 ``False`` 时**立即返回 ``None``**，且**不发起任何
    网络请求**，也不解析 / 读取 webhook URL（Req 14.4：关闭时零请求）。
    开启时委托给 :func:`push_to_feishu`，并返回其 :class:`PushResult`。

    Args:
        markdown: 周报 Markdown 文本。
        cfg: 飞书配置（``enabled`` 与 ``webhook_url``）。
        sender: 可选网络接缝，透传给 :func:`push_to_feishu`（便于测试）。

    Returns:
        关闭时返回 ``None``；开启时返回 :class:`PushResult`。
    """
    if not cfg.enabled:
        return None
    return push_to_feishu(markdown, cfg.webhook_url, sender=sender)
