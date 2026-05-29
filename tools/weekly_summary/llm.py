"""LLM_Narrator（``llm.py``）— Req 8、9（可选，**默认关闭**）。

职责：在用户**显式开启** LLM 时，基于**摘要化结构化要点**调用外部 LLM，生成
「本周主题归纳 + 下周建议」文本（Req 9.1）。默认关闭，关闭时不发起任何外部请求
（Req 8.1、8.4）。

设计依据：design.md「Components and Interfaces / LLM_Narrator（`llm.py`）— Req 8、9」
与「核心设计原则：隐私与数据边界」。

隐私边界（第一性约束）
----------------------
本模块是**唯一**构造「将要离开本地、发往外部 LLM」之数据的地方，其安全性建立在
两条结构性保证之上：

1. :class:`LLMInput` 在**类型层面**就只含三类摘要字段——``project_names``、
   ``topic_keywords``、``commit_subjects``。它**不含**任何承载原始对话的字段
   （没有 ``user_prompts``、没有原始 transcript 文本）。因此「把原始对话发出去」
   在类型上就无法表达（Req 8.5、8.6）。
2. :func:`build_llm_input` 是**唯一**构造 :class:`LLMInput` 的入口，且它**从不读取**
   :class:`~weekly_summary.models.CodexSession` 的 ``user_prompts``。外发负载里出现的
   一切文本，只可能来自项目名、（非对话派生的）主题关键词与 git commit 标题。
   这使得 Property 16（「任一 user_prompt 原文都不是外发负载的子串」）在结构上成立。

可注入的网络出口（injectable client seam）
------------------------------------------
:func:`narrate` 的全部出网行为都收敛到一个**可注入的 ``client`` 形参**：

- ``client is None`` 时使用基于标准库 ``urllib`` 的默认 OpenAI 风格实现
  （:func:`_default_urllib_client`），**不引入任何第三方依赖**。
- 测试可传入自定义 ``client`` 拦截/记录出网调用，从而：
  * 验证 Property 14（关闭时**零外发**）——关闭时 :func:`narrate` 在触达 ``client``
    之前就返回 ``None``，故被注入的 ``client`` 记录到零次调用；
  * 验证 Property 16（开启时**仅外发摘要**）——被注入的 ``client`` 收到的
    :class:`LLMRequest` 即为完整出网负载，可断言其中不含任何原始对话文本。

凭证来源
--------
API key **只从环境变量** ``WEEKLY_SUMMARY_LLM_API_KEY`` 读取（:func:`read_api_key`），
**绝不**从 TOML 配置读取（密钥不入库，见 design「凭证不入库」）。调用方可显式传入
``api_key``；为 ``None`` 时 :func:`narrate` 回退到 :func:`read_api_key`，确保唯一来源
始终是该环境变量。

错误语义
--------
- **关闭**（``cfg.enabled is False``）→ 返回 ``None``，不发起任何外部请求（Req 8.1、8.4）。
- **开启但缺凭证** → 抛 :class:`MissingCredentialError`（见下方「为何抛异常而非返回
  None」）。
- **开启且有凭证、但调用失败**（网络 / HTTP / 解析）→ 记录失败并返回 ``None``，由
  上层继续生成**不含 LLM 章节**的周报（Req 9.2）。

为何「缺凭证」抛异常而非返回 None
--------------------------------
design 的接口注释把「缺凭证」与「调用失败」都标作返回 ``None``，但 Req 9.2 与 9.3 是
两种**需要被区分**的情形：

- Req 9.2（调用失败）要求**静默降级**——记录失败、照常出周报。
- Req 9.3（缺凭证）要求**返回一条「说明缺失凭证」的错误信息**，再出不含 LLM 章节的
  周报。

用一个**专门的异常类型** :class:`MissingCredentialError` 承载该描述性错误信息，能让
编排层（``summarize.py``，Task 13）一眼区分这两种情形：捕获 :class:`MissingCredentialError`
即可打印缺凭证提示并继续渲染（满足 Req 9.3 对「描述性错误信息」的要求），而
``narrate`` 返回 ``None`` 则对应「关闭」或「调用失败」的降级路径（Req 9.2）。
:func:`narrate` 本身**不会**让异常击穿整条流水线——异常由编排层捕获处理。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import AggregatedReport, LLMConfig

__all__ = [
    "API_KEY_ENV_VAR",
    "LLMInput",
    "LLMRequest",
    "LLMClient",
    "MissingCredentialError",
    "read_api_key",
    "build_llm_input",
    "narrate",
]

_LOGGER = logging.getLogger(__name__)

# API key 的唯一来源（环境变量；绝不从 TOML 读取，密钥不入库）。
API_KEY_ENV_VAR = "WEEKLY_SUMMARY_LLM_API_KEY"

# 默认 OpenAI 风格 chat completions 端点；按 provider 选择，未知 provider 回退至此。
_PROVIDER_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/chat/completions",
}
_DEFAULT_ENDPOINT = _PROVIDER_ENDPOINTS["openai"]

# 默认网络出口的超时（秒），避免编排层被外部服务长时间阻塞。
_REQUEST_TIMEOUT_SECONDS = 30


class MissingCredentialError(Exception):
    """LLM 已开启但缺少 API 凭证时抛出（Req 9.3）。

    错误消息为描述性文本，指明缺失的环境变量名，供编排层打印并据此生成
    **不含 LLM 章节**的周报。
    """


# --------------------------------------------------------------------------- #
# 摘要化外发数据模型（隐私边界的类型化体现，Req 8.5、8.6）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LLMInput:
    """发往外部 LLM 的**摘要化**要点——隐私边界的类型化体现（Req 8.5、8.6）。

    本类型**只**包含三类摘要字段，从结构上**排除**了任何原始对话 / transcript：

    - ``project_names``：涉及的项目名（``project_dir`` 的 basename）。
    - ``topic_keywords``：主题关键词（**非**由原始对话派生，见 :func:`build_llm_input`）。
    - ``commit_subjects``：git 提交标题（subject）。

    类型中**不存在** ``user_prompts`` 或任何原始文本字段，因此「把原始 Codex 对话
    发往外部」在类型层面就无法表达。
    """

    project_names: list[str]
    topic_keywords: list[str]
    commit_subjects: list[str]


@dataclass(frozen=True)
class LLMRequest:
    """一次 LLM 调用的完整出网负载——即将「离开本地」的全部数据。

    所有字段均来自 :class:`LLMInput`（经 :func:`_build_messages`）与配置 / 凭证；
    其中 ``messages`` 的文本内容**仅**源自 :class:`LLMInput` 的摘要字段。测试可拦截
    本对象以断言出网负载不含任何原始对话（Property 16）。
    """

    provider: str
    model: str
    api_key: str
    messages: list[dict[str, str]]


class LLMClient(Protocol):
    """可注入的网络出口协议：接收一次 :class:`LLMRequest`，返回 LLM 文本输出。

    这是 :func:`narrate` **唯一**的出网通道。默认实现为
    :func:`_default_urllib_client`（标准库 ``urllib``）；测试可注入自定义实现以
    拦截/记录调用（支撑 Property 14 / 16 的可验证性）。

    约定：调用失败（网络 / HTTP / 解析）应**抛出异常**，由 :func:`narrate` 捕获后
    降级为返回 ``None``（Req 9.2）。
    """

    def __call__(self, request: LLMRequest) -> str: ...


# --------------------------------------------------------------------------- #
# 凭证读取（唯一来源：环境变量）
# --------------------------------------------------------------------------- #
def read_api_key() -> str | None:
    """从环境变量 :data:`API_KEY_ENV_VAR` 读取 API key（唯一来源）。

    Returns:
        去除首尾空白后的非空 key；未设置或为空白时返回 ``None``。绝不从 TOML 配置
        读取（密钥不入库）。
    """
    value = os.environ.get(API_KEY_ENV_VAR)
    if value is None:
        return None
    value = value.strip()
    return value or None


# --------------------------------------------------------------------------- #
# 构造外发摘要（唯一的外发数据构造入口，隐私边界）
# --------------------------------------------------------------------------- #
def _basename(path: str) -> str:
    """返回路径 basename（去除尾部分隔符）；为空时回退原字符串。"""
    return Path(path).name or path


def build_llm_input(report: AggregatedReport) -> LLMInput:
    """从 :class:`AggregatedReport` 构造**摘要化**的 :class:`LLMInput`（Req 8.5、8.6）。

    这是**唯一**构造外发数据的函数。其产出的字段来源**严格受限**于非对话数据：

    - ``project_names``：``report.distribution`` 中各项目 ``project_dir`` 的 basename
      （跳过保留桶 :data:`~weekly_summary.aggregate.UNMATCHED_PROJECT`，它不是真实项目名），
      按分布顺序去重。
    - ``commit_subjects``：``report.repo_commits`` 中**所有**提交的 ``subject``，按出现
      顺序保留（git 提交标题，Req 8.5 明确允许外发）。
    - ``topic_keywords``：由**项目名与仓库标识**（``repo_commits`` 的 ``repo_id``）这类
      **非对话派生**的确定性标识汇总、去重、排序得到。

    关于 ``topic_keywords`` 的来源选择（**关键隐私说明**）：本函数**从不读取**
    :class:`~weekly_summary.models.CodexSession` 的 ``user_prompts``——即原始 User_Prompt
    文本绝不进入任何外发字段（Req 8.6）。当前尚无「不泄露原文的」关键词抽取能力
    （与 ``export.py`` 把 codex ``themes`` 留空的取舍一致），因此这里用项目名 / 仓库标识
    这类安全标识来充当主题关键词，而非从对话原文派生。如此既给出有意义的关键词，又
    在结构上保证 Property 16（任一 ``user_prompt`` 原文都不是外发负载的子串）成立。

    Args:
        report: 聚合后的完整周报数据模型。

    Returns:
        仅含摘要字段的 :class:`LLMInput`。
    """
    # 延迟导入避免与 aggregate 形成模块级循环依赖；仅取保留桶常量。
    from .aggregate import UNMATCHED_PROJECT

    project_names: list[str] = []
    seen_projects: set[str] = set()
    for item in report.distribution:
        if item.project_dir == UNMATCHED_PROJECT:
            continue  # 保留桶不是真实项目名，跳过。
        name = _basename(item.project_dir)
        if name not in seen_projects:
            seen_projects.add(name)
            project_names.append(name)

    # 所有提交标题（subject），按出现顺序保留。仅来自 git，非对话内容。
    commit_subjects: list[str] = [
        commit.subject
        for repo in report.repo_commits
        for commit in repo.commits
    ]

    # 主题关键词：项目名 ∪ 仓库标识（repo_id），去重后排序。均为非对话派生的安全标识。
    repo_ids = {repo.repo_id for repo in report.repo_commits if repo.commits}
    topic_keywords: list[str] = sorted(set(project_names) | repo_ids)

    return LLMInput(
        project_names=project_names,
        topic_keywords=topic_keywords,
        commit_subjects=commit_subjects,
    )


# --------------------------------------------------------------------------- #
# 出网负载构造（仅基于 LLMInput 的摘要字段）
# --------------------------------------------------------------------------- #
def _build_messages(llm_input: LLMInput) -> list[dict[str, str]]:
    """把 :class:`LLMInput` 渲染为 OpenAI 风格 chat ``messages``。

    **仅**使用 :class:`LLMInput` 的三个摘要字段拼装提示文本——这是出网文本内容的
    唯一来源，确保不含任何原始对话（Req 8.6）。
    """
    project_block = "、".join(llm_input.project_names) or "（无）"
    keyword_block = "、".join(llm_input.topic_keywords) or "（无）"
    subject_block = (
        "\n".join(f"- {subject}" for subject in llm_input.commit_subjects)
        or "（无）"
    )
    system_content = (
        "你是一个开发周报助手。请仅依据用户提供的摘要要点进行归纳，"
        "不要臆造未提供的信息。"
    )
    user_content = (
        "以下是本周开发活动的摘要要点（不含任何原始对话内容）：\n\n"
        f"涉及项目：{project_block}\n"
        f"主题关键词：{keyword_block}\n"
        f"本周提交标题：\n{subject_block}\n\n"
        "请基于以上摘要，用中文输出：1) 本周主题归纳；2) 下周建议。"
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _default_urllib_client(request: LLMRequest) -> str:
    """默认网络出口：用标准库 ``urllib`` 发起 OpenAI 风格 chat completions 调用。

    不引入任何第三方依赖。失败（网络 / HTTP / 解析）会向上抛出异常，由
    :func:`narrate` 捕获后降级（Req 9.2）。
    """
    endpoint = _PROVIDER_ENDPOINTS.get(request.provider, _DEFAULT_ENDPOINT)
    body = json.dumps(
        {"model": request.model, "messages": request.messages}
    ).encode("utf-8")
    http_request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {request.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(  # noqa: S310 - endpoint 固定为 https OpenAI 风格端点
        http_request, timeout=_REQUEST_TIMEOUT_SECONDS
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    # 解析 OpenAI 风格响应；结构不符会抛 KeyError/IndexError，由 narrate 捕获。
    return payload["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------- #
# 主入口：narrate
# --------------------------------------------------------------------------- #
def narrate(
    llm_input: LLMInput,
    cfg: LLMConfig,
    api_key: str | None,
    *,
    client: LLMClient | None = None,
) -> str | None:
    """在开启且有凭证时生成主题归纳与下周建议（Req 9.1）。

    Args:
        llm_input: 由 :func:`build_llm_input` 构造的摘要化外发要点。
        cfg: LLM 配置；``cfg.enabled is False`` 时直接返回 ``None``（零外发，Req 8.1、8.4）。
        api_key: 调用方可显式传入；为 ``None`` 时回退到 :func:`read_api_key`
            （唯一来源为环境变量 :data:`API_KEY_ENV_VAR`）。
        client: 可注入的网络出口（:class:`LLMClient`）；为 ``None`` 时使用默认
            :func:`_default_urllib_client`。这是**唯一**的出网通道（支撑 Property 14/16）。

    Returns:
        LLM 生成的「主题归纳 + 下周建议」文本；当 LLM 关闭或调用失败时返回 ``None``
        （Req 8.1、8.4、9.2）。

    Raises:
        MissingCredentialError: LLM 已开启但缺少 API 凭证（Req 9.3）；由编排层捕获，
            打印缺凭证提示并生成不含 LLM 章节的周报。
    """
    # 关闭：不构造请求、不触达 client —— 零外发（Req 8.1、8.4）。
    if not cfg.enabled:
        return None

    # 凭证仅来自显式入参或环境变量；二者皆无则报缺凭证（Req 9.3）。
    resolved_key = api_key if api_key else read_api_key()
    if not resolved_key:
        raise MissingCredentialError(
            f"LLM 已开启但缺少 API 凭证：请设置环境变量 {API_KEY_ENV_VAR}。"
            f"本次将生成不含 LLM 章节的周报。"
        )

    request = LLMRequest(
        provider=cfg.provider,
        model=cfg.model,
        api_key=resolved_key,
        messages=_build_messages(llm_input),
    )

    call: LLMClient = client if client is not None else _default_urllib_client
    try:
        return call(request)
    except Exception as exc:  # noqa: BLE001 - 调用失败需降级而非中断流水线（Req 9.2）
        _LOGGER.warning(
            "LLM 调用失败，将生成不含 LLM 章节的周报：%s", exc
        )
        return None
