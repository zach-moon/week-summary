"""LLM 外发摘要边界属性测试（Task 11.2 / Property 16）。

本文件遵循「one property per file」约定，**仅**实现 Property 16：

- **Property 16**（Req 8.5、8.6）：LLM 开启时，外发负载**仅**含摘要字段
  （项目名、主题关键词、commit 标题），**绝不**含任何原始 Codex 对话——任一
  ``user_prompt`` 原文都不是外发负载的子串。

实现手段：向 :func:`weekly_summary.llm.narrate` 注入一个**记录型 client**
（:class:`_RecordingClient`），它把每次收到的 :class:`~weekly_summary.llm.LLMRequest`
原样记录下来并返回固定文本，从而可在开启时检视完整出网负载。

为使「原文是否泄露」的子串检查具备意义（而非因巧合的单字符子串产生假阴性），
原始 ``user_prompt`` 一律用一个**显著 sentinel 标记**包裹，而摘要派生字段
（项目名 / commit 标题 / repo_id）的生成空间被约束为**不含**该 sentinel。
"""

from __future__ import annotations

import json
from datetime import date

import hypothesis.strategies as st
from hypothesis import given

from weekly_summary.llm import LLMInput, LLMRequest, build_llm_input, narrate
from weekly_summary.models import (
    AggregatedReport,
    CodexSession,
    Commit,
    LLMConfig,
    ProjectDistribution,
    RepoCommits,
)


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
# 生成器：构造含「带显著标记的原始 user_prompts」的 AggregatedReport
# --------------------------------------------------------------------------- #
# 原始 user_prompt 的显著标记（sentinel）。摘要字段一律不含此标记，从而使
# 「原文是否泄露到外发负载」的子串检查具备意义（task 要求）。
_RAW_SENTINEL = "Zq7_RAW_PROMPT_Zq7"

# 摘要派生字段（项目名 / commit 标题 / repo_id）的文本：可打印 ASCII，且不含 sentinel。
_safe_text = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    max_size=24,
).filter(lambda s: _RAW_SENTINEL not in s)


@st.composite
def _raw_user_prompt(draw: st.DrawFn) -> str:
    """构造一条带 sentinel 包裹的原始 User_Prompt 文本（必非空）。"""
    body = draw(st.text(max_size=30))
    return f"{_RAW_SENTINEL}{body}{_RAW_SENTINEL}"


@st.composite
def _reports_with_raw_prompts(draw: st.DrawFn) -> AggregatedReport:
    """生成含原始 user_prompts（带 sentinel）的报告，供 Property 16 验证。"""
    n_projects = draw(st.integers(min_value=1, max_value=4))
    project_dirs = [f"/proj/{draw(_safe_text)}/p{i}" for i in range(n_projects)]

    distribution = [
        ProjectDistribution(
            project_dir=pd,
            commit_count=draw(st.integers(min_value=0, max_value=5)),
            session_count=draw(st.integers(min_value=0, max_value=5)),
        )
        for pd in project_dirs
    ]

    repo_commits: list[RepoCommits] = []
    for i in range(n_projects):
        subjects = draw(st.lists(_safe_text, max_size=4))
        commits = [
            Commit(repo_id=f"repo{i}", date=date(2026, 5, 26), subject=subject)
            for subject in subjects
        ]
        repo_commits.append(
            RepoCommits(repo_id=f"repo{i}", repo_path=project_dirs[i], commits=commits)
        )

    sessions: list[CodexSession] = []
    n_sessions = draw(st.integers(min_value=1, max_value=4))
    for j in range(n_sessions):
        prompts = draw(st.lists(_raw_user_prompt(), min_size=1, max_size=3))
        project_dir = draw(st.sampled_from(project_dirs))
        sessions.append(
            CodexSession(
                session_id=f"s{j}",
                project_dir=project_dir,
                date=date(2026, 5, 26),
                user_prompts=prompts,
                prompt_count=len(prompts),
            )
        )

    return AggregatedReport(
        report_identifier="2026-W22",
        week_start=date(2026, 5, 25),
        week_end=date(2026, 5, 31),
        distribution=distribution,
        repo_commits=repo_commits,
        repo_sessions=sessions,
        total_commits=sum(len(rc.commits) for rc in repo_commits),
        total_sessions=len(sessions),
        total_user_prompts=sum(s.prompt_count for s in sessions),
    )


def _serialize_outbound(request: LLMRequest) -> str:
    """把一次出网 :class:`LLMRequest` 序列化为完整负载文本（用于子串检查）。"""
    serialized = json.dumps(
        {
            "provider": request.provider,
            "model": request.model,
            "api_key": request.api_key,
            "messages": request.messages,
        },
        ensure_ascii=False,
    )
    # 额外拼上各 message 的原始（未转义）正文，确保子串检查覆盖未转义文本。
    raw_concat = serialized + "".join(
        str(message.get("content", "")) for message in request.messages
    )
    return raw_concat


@given(report=_reports_with_raw_prompts())
def test_property_16_llm_outbound_only_summary_no_raw_transcript(
    report: AggregatedReport,
) -> None:
    # Feature: weekly-dev-report, Property 16: LLM 开启时仅外发摘要且不含原始对话
    """**Validates: Requirements 8.5, 8.6**

    LLM 开启时，``narrate`` 经唯一出网通道发送的负载只由 ``build_llm_input`` 的摘要
    字段派生；任一原始 ``user_prompt`` 文本都不应作为子串出现在外发负载中。
    """
    recorder = _RecordingClient()
    llm_input = build_llm_input(report)

    # LLMInput 在类型层面仅含三类摘要字段，结构上排除原始 transcript。
    assert set(vars(llm_input).keys()) == {
        "project_names",
        "topic_keywords",
        "commit_subjects",
    }

    # 提供 api_key，使流程一路触达被注入的 client（产生一次可检视的出网负载）。
    result = narrate(llm_input, LLMConfig(enabled=True), "test-api-key", client=recorder)

    # 开启且有凭证：恰好一次出网调用。
    assert result == "FAKE_LLM_OUTPUT"
    assert len(recorder.requests) == 1

    payload = _serialize_outbound(recorder.requests[0])

    # 关键隐私断言：sentinel（原始 prompt 的标记）绝不出现在外发负载中，
    # 因而任一 user_prompt 原文都不可能是负载的子串。
    assert _RAW_SENTINEL not in payload
    for session in report.repo_sessions:
        for prompt in session.user_prompts:
            assert prompt not in payload
