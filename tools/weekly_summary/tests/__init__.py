"""Weekly_Summary_CLI 测试包（pytest + Hypothesis）。

约定：
- 属性测试每条放在独立测试文件中，并以注释标注其对应的设计属性：
  ``# Feature: weekly-dev-report, Property {n}: {text}``
- 每个属性测试至少运行 100 次随机迭代（Hypothesis ``max_examples>=100``）。
"""
