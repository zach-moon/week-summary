"""pytest / Hypothesis 共享测试配置。

注册并选用一个 Hypothesis profile，确保属性测试至少运行 100 次随机迭代
（与设计「Testing Strategy」中 ``max_examples>=100`` 的约定一致）。
"""

from __future__ import annotations

from hypothesis import HealthCheck, settings

# 至少 100 次随机迭代（设计 Testing Strategy 约定）。
settings.register_profile(
    "weekly-summary",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("weekly-summary")
