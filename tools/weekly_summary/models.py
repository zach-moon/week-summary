"""数据模型（dataclasses）。

本模块定义 Weekly_Summary_CLI（LOCAL tier）在内存中传递的全部数据结构，
对应设计文档「Components and Interfaces」与「Data Models」两章的字段与类型注解。

设计约定：
- 所有模型均为 ``@dataclass``；配置类与时间窗等不可变模型使用 ``frozen=True``。
- 类型注解遵循 Python 3.10+ 语法（``str | None``、``list[str]`` 等）。
- 本文件只定义数据结构，不包含任何采集 / 聚合 / 渲染 / 导出逻辑——
  这些逻辑属于各自的模块与后续任务。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

__all__ = [
    "Commit",
    "RepoCommits",
    "CodexSession",
    "ProjectDistribution",
    "AggregatedReport",
    "Config",
    "WeekWindow",
    "LLMConfig",
    "FeishuConfig",
]


# --------------------------------------------------------------------------- #
# 配置模型（Config_Loader 产物，Req 1）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LLMConfig:
    """LLM_Narrator 配置（Req 8、9）。

    API key 不写入 TOML，仅从环境变量 ``WEEKLY_SUMMARY_LLM_API_KEY`` 读取。
    """

    enabled: bool = False  # Req 8.2 默认关闭（隐私优先）
    provider: str = "openai"  # e.g. "openai" | "anthropic"
    model: str = "gpt-4o-mini"


@dataclass(frozen=True)
class FeishuConfig:
    """Feishu_Integration 配置（Req 14）。

    ``webhook_url`` 视为机密，建议由环境变量
    ``WEEKLY_SUMMARY_FEISHU_WEBHOOK`` 覆盖。
    """

    enabled: bool = False
    webhook_url: str = ""


@dataclass(frozen=True)
class Config:
    """解析 ``~/.config/weekly-summary.toml`` 得到的强类型配置对象（Req 1）。"""

    repos: list[str]  # 仓库绝对路径列表
    output_dir: str = "dev_log"  # Req 1.5
    author: str | None = None  # 作者过滤（Req 2.4）
    export_enabled: bool = True  # Req 10
    push_target: str | None = None  # rsync over SSH 目标, e.g. "user@host:/srv/weekly/data/"
    llm: LLMConfig = field(default_factory=LLMConfig)
    feishu: FeishuConfig = field(default_factory=FeishuConfig)


# --------------------------------------------------------------------------- #
# 时间窗模型（Week_Window，Req 4）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class WeekWindow:
    """本周时间窗与 Report_Identifier（Req 4）。"""

    start: datetime  # 本地时区, 周一 00:00:00
    end: datetime  # 默认 = now；指定周时 = 周日 23:59:59
    report_identifier: str  # "<ISO-year>-W<ISO-week, 两位补零>", e.g. "2026-W22"


# --------------------------------------------------------------------------- #
# Git 采集模型（Git_Collector，Req 2）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Commit:
    """单条 Git 提交记录（Req 2.2）。"""

    repo_id: str  # 仓库标识（取 basename 或配置别名）
    date: date  # 提交日期（本地时区）
    subject: str  # 提交标题


@dataclass(frozen=True)
class RepoCommits:
    """单个仓库在时间窗内的提交集合（Req 2.1、2.5）。"""

    repo_id: str
    repo_path: str
    commits: list[Commit]  # 时间窗内（可能为空, Req 2.5）


# --------------------------------------------------------------------------- #
# Codex 采集模型（Codex_Collector，Req 3）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CodexSession:
    """单次 Codex CLI 会话的摘要（Req 3.7）。"""

    session_id: str  # 取自文件名 uuid
    project_dir: str  # 来自首行 session_meta payload.cwd
    date: date  # 来自 payload.timestamp
    user_prompts: list[str]  # 真实 User_Prompt 文本（已排除注入上下文）
    prompt_count: int  # == len(user_prompts) (Req 3.7)


# --------------------------------------------------------------------------- #
# 聚合模型（Report_Aggregator，Req 5）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProjectDistribution:
    """单个项目目录的时间分布条目（Req 5.1、5.2）。"""

    project_dir: str
    commit_count: int
    session_count: int


@dataclass(frozen=True)
class AggregatedReport:
    """聚合后的完整周报数据模型（Req 5、10.3）。"""

    report_identifier: str
    week_start: date
    week_end: date
    distribution: list[ProjectDistribution]  # 含零活动项目, 已排序 (Req 5.1, 5.3)
    repo_commits: list[RepoCommits]  # 各仓库 commit 列表
    repo_sessions: list[CodexSession]  # 各项目 codex 会话
    total_commits: int
    total_sessions: int
    total_user_prompts: int
    llm_suggestions: str | None = None  # 仅当 LLM 开启
