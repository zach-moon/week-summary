"""Weekly_Summary_CLI — 开发周报自动生成工具（LOCAL tier）。

包内模块（部分在后续任务实现）：

- ``models``        数据模型（dataclasses）—— 已实现
- ``config``        Config_Loader
- ``week_window``   Week_Window 逻辑
- ``collectors``    Git_Collector / Codex_Collector
- ``aggregate``     Report_Aggregator
- ``render``        Markdown_Renderer
- ``export``        Data_Exporter（JSON 序列化/反序列化）
- ``llm``           LLM_Narrator（可选）
- ``feishu``        Feishu_Integration（可选）
- ``summarize``     CLI 入口 / 编排层
"""

__all__ = ["models"]
