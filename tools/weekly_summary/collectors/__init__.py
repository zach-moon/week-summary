"""采集器子包。

- ``git_collector``   Git_Collector（Req 2）—— 已实现
- ``codex_collector`` Codex_Collector（Req 3）—— 后续任务实现

本包额外定义采集器共享的轻量警告类型 ``CollectorWarning``：设计文档中
``collect_commits`` / ``collect_sessions`` 的签名返回 ``list[Warning]``，
这里用一个自定义不可变 dataclass 表达「非致命、可降级」的警告（Req 2.3、3.5、3.6），
以避免与 Python 内置的 ``Warning`` 异常基类混淆。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["CollectorWarning"]


@dataclass(frozen=True)
class CollectorWarning:
    """采集过程中的非致命警告（Req 2.3、3.5、3.6）。

    采集器遇到可跳过的问题时（如某路径不是有效 git 仓库、某 JSONL 文件损坏、
    会话目录缺失），不会中止整个流程，而是收集一条 ``CollectorWarning`` 并继续。

    属性:
        source:  触发该警告的来源标识（仓库路径或会话文件路径），用于定位。
        message: 人类可读的警告说明。
    """

    source: str
    message: str
