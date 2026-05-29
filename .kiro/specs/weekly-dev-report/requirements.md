# Requirements Document

## Introduction

本功能构建一个「开发周报自动生成」工具，用于在周末花约 5 分钟自动总结「本周做了什么」。

核心动机：`git log` 只能告诉你**改了哪些文件**，却说不清**为什么改**；而 Codex CLI 的会话记录保留了思考过程（在想什么、在学什么、卡在哪里）。把两类数据源合并，才能形成一份真正可回顾的复盘——即使 6 个月后再看也能看懂。

本功能包含两个部分：

1. **CLI 工具（Weekly_Summary_CLI）**：合并「多个 Git 仓库的提交记录」与「`~/.codex/sessions/` 下本周的 Codex 会话记录」，生成一份中文 Markdown 周报，落地到 `dev_log/<year>-W<week>.md`；并可选导出结构化数据供前端消费。
2. **可视化前端（Visualization_Frontend）**：一个带登录页、设计感强（「类似 Apple 官网」的审美）的展示界面，采用 Next.js + Tailwind CSS 实现，以 Docker 容器形式部署在用户自己的服务器上，用于展示「我学到了什么」。Next.js 同时提供 GitHub OAuth 令牌交换与会话所需的轻量后端，并从挂载的数据卷读取 JSON 周报数据。

隐私是硬约束：默认全部本地处理；LLM 调用默认关闭且可选；即便开启 LLM，也只发送**摘要化的结构化要点**（项目名 / 主题关键词 / commit 标题），**绝不发送原始对话内容**。

> 说明：本文档中 EARS 关键字（WHEN / WHILE / IF / THEN / WHERE / THE / SHALL）保留英文以符合 EARS 规范，其余描述使用中文。文档末尾的「设计阶段已确定的关键决策」记录了进入设计阶段前已敲定的技术选型（GitHub OAuth、Docker、Next.js + Tailwind CSS、JSON 结构化导出、飞书 Webhook）。

## Glossary

- **Weekly_Summary_CLI**: 命令行工具整体，入口为 `python3 tools/weekly_summary/summarize.py`，负责采集、聚合、渲染与（可选）导出。
- **Config_Loader**: 负责读取并解析配置文件 `~/.config/weekly-summary.toml`（TOML 格式）的子系统。
- **Git_Collector**: 负责从用户配置的多个 Git 仓库中采集指定时间窗内提交记录的子系统。
- **Codex_Collector**: 负责从 `~/.codex/sessions/` 读取并解析本周 Codex CLI 会话日志的子系统。
- **Report_Aggregator**: 负责将采集到的数据按项目目录聚合、统计的子系统。
- **Markdown_Renderer**: 负责将聚合后的数据模型渲染为中文 Markdown 周报文本的子系统（对应 `render.py`）。
- **Data_Exporter**: 负责将聚合后的数据模型序列化为结构化数据文件（供前端消费）的子系统。
- **LLM_Narrator**: 可选子系统，在用户显式开启时，基于摘要化结构化要点调用 LLM 生成主题归纳与下周建议。
- **Visualization_Frontend**: 部署在用户自有服务器上的可视化展示前端，采用 Next.js + Tailwind CSS 实现并以 Docker 容器形式打包，含登录页，从挂载的数据目录读取 JSON 周报数据。
- **Auth_Service**: 为 Visualization_Frontend 提供登录认证与访问控制的服务组件，基于 GitHub OAuth 2.0 授权码流程（authorization code flow）实现，由 Next.js 后端承载令牌交换与服务端会话管理。
- **Allow_List（账户允许名单）**: 在前端配置中声明的、被授权访问 Visualization_Frontend 的 GitHub 账户集合（默认仅包含拥有者本人）。
- **Feishu_Integration**: 可选的飞书（Lark）集成组件，通过自定义机器人 Webhook（incoming webhook）实现 CLI 向飞书的单向推送。
- **Week_Window（本周时间窗）**: 从本周一 00:00:00（本地时区）到当前时刻的时间区间。
- **Report_Identifier（周报标识）**: 形如 `<year>-W<week>` 的标识，其中 `<week>` 为 ISO 8601 周序号（两位、补零），例如 `2026-W22`。
- **Codex_Session_Log**: `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<uuid>.jsonl` 路径下记录单次 Codex CLI 会话的 JSONL 日志文件（每行一个 JSON 对象）。每行含顶层 `type` 字段，取值为 `session_meta`、`turn_context`、`event_msg` 或 `response_item`；首行 `type` 为 `session_meta`，其 `payload.cwd` 为会话所属项目工作目录、`payload.git` 含 `commit_hash` / `branch` / `repository_url`、`payload.timestamp` 标识会话时间。
- **User_Prompt（用户提问）**: Codex 会话中由用户真实发起的提问条目，对应 `type == "response_item"` 且 `payload.type == "message"`、`payload.role == "user"`、含 `input_text` 内容条目的行；不包含被注入的上下文包装消息（其文本被 `<environment_context>`、`<collaboration_mode>`、`<skills_instructions>`、`<plugins_instructions>` 等标签包裹）。
- **Injected_Context_Message（注入上下文消息）**: `role == "user"` 但内容由系统注入的包装消息，其文本被形如 `<environment_context>` 的标签包裹，不属于 User_Prompt。
- **Structured_Export（结构化导出）**: Data_Exporter 输出的 JSON 数据文件，写入 `dev_log/data/<Report_Identifier>.json`，作为 CLI 与前端之间的数据契约；Visualization_Frontend 从挂载的数据目录读取该 JSON 文件进行展示。

## Requirements

### Requirement 1: 加载与解析配置文件

**User Story:** 作为开发者，我希望工具从固定路径读取我的仓库列表与选项配置，以便无需每次手动指定参数即可生成周报。

#### Acceptance Criteria

1. WHEN Weekly_Summary_CLI 启动且未通过命令行指定配置路径，THE Config_Loader SHALL 从 `~/.config/weekly-summary.toml` 读取配置。
2. WHEN 配置文件为合法 TOML 格式，THE Config_Loader SHALL 将其解析为配置对象，且该对象包含仓库列表与可选项字段。
3. IF 配置文件不存在，THEN THE Config_Loader SHALL 返回一条提示「配置文件缺失」的错误信息，并在错误信息中包含期望的配置文件绝对路径。
4. IF 配置文件存在但 TOML 语法非法，THEN THE Config_Loader SHALL 返回一条包含出错位置（行号或键名）的描述性错误信息。
5. WHERE 配置中提供了输出目录选项，THE Weekly_Summary_CLI SHALL 使用该目录作为周报输出目录。
6. THE Weekly_Summary_CLI SHALL 提供一份默认配置文件模板，模板包含仓库列表、输出目录与 LLM 开关字段，且 LLM 开关默认值为关闭。

### Requirement 2: 跨多仓库采集 Git 提交记录

**User Story:** 作为同时维护多个项目的开发者，我希望工具汇总本周所有仓库的提交，以便一次性看到全部产出。

#### Acceptance Criteria

1. WHEN 给定一个仓库列表与 Week_Window，THE Git_Collector SHALL 采集每个仓库中提交时间落在 Week_Window 内的提交记录。
2. THE Git_Collector SHALL 为每条采集到的提交记录保留所属仓库标识、提交日期与提交标题（subject）。
3. IF 仓库列表中某个路径不是有效的 Git 仓库，THEN THE Git_Collector SHALL 记录一条标识该路径的警告信息，并继续处理列表中其余仓库。
4. WHERE 配置指定了作者过滤条件，THE Git_Collector SHALL 仅采集提交作者匹配该条件的提交记录。
5. WHEN 某个仓库在 Week_Window 内没有提交记录，THE Git_Collector SHALL 为该仓库返回空提交集合，且不产生错误。

### Requirement 3: 采集与解析 Codex 会话记录

**User Story:** 作为开发者，我希望工具读取本周 Codex CLI 会话，以便把「我问了什么、在想什么」纳入周报。

#### Acceptance Criteria

1. WHEN 给定 Week_Window，THE Codex_Collector SHALL 从 `~/.codex/sessions/<YYYY>/<MM>/<DD>/` 目录树读取文件名形如 `rollout-<timestamp>-<uuid>.jsonl` 且会话时间落在 Week_Window 内的 Codex_Session_Log 文件。
2. WHEN 解析一个 Codex_Session_Log，THE Codex_Collector SHALL 逐行解析 JSONL，并从首行 `type == "session_meta"` 的 `payload.cwd` 读取会话所属项目目录、从 `payload.timestamp` 读取会话日期。
3. WHEN 提取 User_Prompt，THE Codex_Collector SHALL 仅选取 `type == "response_item"` 且 `payload.type == "message"`、`payload.role == "user"` 并含 `input_text` 内容条目的行。
4. WHEN 遇到 `role == "user"` 但内容被注入上下文包装标签（如 `<environment_context>`、`<collaboration_mode>`、`<skills_instructions>`、`<plugins_instructions>`）包裹的消息，THE Codex_Collector SHALL 将其判定为 Injected_Context_Message，并将其排除在 User_Prompt 计数与提取之外。
5. IF 某个 Codex_Session_Log 文件内容无法解析，THEN THE Codex_Collector SHALL 跳过该文件、记录一条标识该文件的警告信息，并继续处理其余文件。
6. IF `~/.codex/sessions/` 目录不存在，THEN THE Codex_Collector SHALL 返回空会话集合，并记录一条说明该目录缺失的信息。
7. THE Codex_Collector SHALL 为每个会话保留会话所属项目目录、会话日期与该会话中的 User_Prompt 数量。

### Requirement 4: 本周时间窗界定

**User Story:** 作为开发者，我希望默认就扫描「本周」，以便周末直接运行无需指定日期。

#### Acceptance Criteria

1. WHEN Weekly_Summary_CLI 在未指定时间范围参数的情况下启动，THE Weekly_Summary_CLI SHALL 将 Week_Window 设为本周一 00:00:00（本地时区）至当前时刻。
2. WHERE 用户通过命令行参数指定了目标周，THE Weekly_Summary_CLI SHALL 将 Week_Window 设为该指定周的周一 00:00:00 至周日 23:59:59（本地时区）。
3. THE Weekly_Summary_CLI SHALL 依据 Week_Window 的起始日期按 ISO 8601 规则计算 Report_Identifier。

### Requirement 5: 按项目目录聚合时间分布

**User Story:** 作为开发者，我希望看到精力在各项目间的分布，以便了解本周重心。

#### Acceptance Criteria

1. WHEN Git 提交记录与 Codex 会话记录采集完成，THE Report_Aggregator SHALL 为配置中的每个项目目录创建一个时间分布条目，包括本周提交数与 Codex 会话数均为零的项目。
2. THE Report_Aggregator SHALL 为每个项目目录的时间分布条目计算该项目的 Codex 会话总数与 commit 总数。
3. THE Report_Aggregator SHALL 按 commit 数与 Codex 会话数对项目时间分布条目降序排序。

### Requirement 6: 生成中文 Markdown 周报

**User Story:** 作为开发者，我希望得到一份结构清晰的中文 Markdown 周报，以便快速阅读与归档。

#### Acceptance Criteria

1. WHEN 聚合数据准备就绪，THE Markdown_Renderer SHALL 生成一份中文 Markdown 文档，文档标题包含 Report_Identifier 与 Week_Window 的起止日期（格式 `YYYY-MM-DD`）。
2. THE Markdown_Renderer SHALL 在周报中包含「时间分布（按项目目录聚合）」章节，逐项列出每个项目的 Codex 会话数与 commit 数。
3. THE Markdown_Renderer SHALL 在周报中包含「本周做了什么（commit）」章节，按仓库分组并列出带日期的提交标题。
4. THE Markdown_Renderer SHALL 在周报中包含「我提了什么关键问题（codex）」章节，按仓库分组列出主题与用户卡住的关键问题。
5. THE Markdown_Renderer SHALL 在周报中包含「数字」章节，列出 commit 总数、Codex 会话总数与 User_Prompt 总数。
6. WHERE LLM_Narrator 处于开启状态，THE Markdown_Renderer SHALL 在周报中包含「自动建议（可选，LLM）」章节，展示下周建议。
7. WHERE LLM_Narrator 处于关闭状态，THE Markdown_Renderer SHALL 省略「自动建议（可选，LLM）」章节，且其余章节正常生成。

### Requirement 7: 周报文件落地

**User Story:** 作为开发者，我希望周报自动落地到固定目录，以便长期沉淀可回顾。

#### Acceptance Criteria

1. WHEN Markdown 周报渲染完成，THE Weekly_Summary_CLI SHALL 将周报写入 `dev_log/<year>-W<week>.md`，其中 `<year>-W<week>` 等于 Report_Identifier。
2. IF 输出目录 `dev_log/` 不存在，THEN THE Weekly_Summary_CLI SHALL 创建该目录后再写入周报文件。
3. IF 目标周报文件已存在，THEN THE Weekly_Summary_CLI SHALL 在覆盖前向用户展示确认提示，并依据用户响应决定是否覆盖。
4. WHEN 目标周报文件尚不存在，THE Weekly_Summary_CLI SHALL 直接写入周报文件，不展示确认提示。
5. IF 目标周报文件已存在且运行于无法获取用户确认的非交互式环境，THEN THE Weekly_Summary_CLI SHALL 跳过覆盖、保留原文件，并输出一条说明已跳过覆盖的提示信息。
6. WHEN 周报文件成功写入，THE Weekly_Summary_CLI SHALL 向用户输出周报文件的绝对路径。

### Requirement 8: 隐私与本地处理边界

**User Story:** 作为重视隐私的开发者，我希望默认所有数据都在本地处理，以便我的代码与对话不外泄。

#### Acceptance Criteria

1. WHILE LLM_Narrator 处于关闭状态，THE Weekly_Summary_CLI SHALL 仅在本地完成全部采集、聚合与渲染，不发起任何外部网络请求。
2. THE Weekly_Summary_CLI SHALL 将 LLM 调用默认配置为关闭。
3. WHEN 配置文件中将 LLM_Narrator 设为开启，THE Weekly_Summary_CLI SHALL 在后续每次运行中均保持开启，且不在启动时重置为关闭。
4. WHILE LLM_Narrator 处于关闭状态，THE Weekly_Summary_CLI SHALL 不向任何外部服务发送摘要数据或其他数据。
5. WHILE LLM_Narrator 处于开启状态，THE LLM_Narrator SHALL 仅向外部 LLM 发送摘要化的结构化要点（项目名、主题关键词、commit 标题）。
6. WHILE LLM_Narrator 处于开启状态，THE LLM_Narrator SHALL 将 Codex 会话的原始对话内容排除在发送给外部 LLM 的数据之外。

### Requirement 9: 可选 LLM 归纳与建议

**User Story:** 作为开发者，我希望可选地让 LLM 帮我归纳主题并给出下周建议，以便获得额外洞察。

#### Acceptance Criteria

1. WHERE LLM_Narrator 在配置中被显式开启，THE LLM_Narrator SHALL 基于摘要化结构化要点生成本周主题归纳与下周建议。
2. IF LLM_Narrator 已开启但调用外部 LLM 失败，THEN THE Weekly_Summary_CLI SHALL 记录该失败信息，并继续生成不含 LLM 章节的周报。
3. WHERE LLM_Narrator 已开启但缺少所需的 API 凭证，THE Weekly_Summary_CLI SHALL 返回一条说明缺失凭证的错误信息，并生成不含 LLM 章节的周报。

### Requirement 10: 结构化数据导出（前端数据契约）

**User Story:** 作为开发者，我希望 CLI 能导出结构化数据，以便可视化前端无需解析 Markdown 即可消费周报数据。

#### Acceptance Criteria

1. WHERE 配置中开启了结构化导出选项，THE Data_Exporter SHALL 将聚合后的数据模型序列化为 JSON 格式的 Structured_Export 文件，并写入 `dev_log/data/<Report_Identifier>.json`。
2. IF 输出目录 `dev_log/data/` 不存在，THEN THE Data_Exporter SHALL 创建该目录后再写入 Structured_Export 文件。
3. THE Data_Exporter SHALL 在 Structured_Export 中包含 Report_Identifier、Week_Window 起止日期、各项目时间分布、各仓库 commit 列表、各仓库 Codex 主题与汇总数字。
4. FOR ALL 合法的聚合数据模型，先序列化为 Structured_Export 再反序列化 SHALL 得到与原数据模型等价的对象（round-trip 属性）。
5. IF 反序列化时遇到非法或损坏的 Structured_Export 内容，THEN THE Data_Exporter SHALL 返回一条描述性错误信息。

### Requirement 11: CLI 默认调用行为

**User Story:** 作为开发者，我希望一条命令就能完成周报生成，以便周末快速完成复盘。

#### Acceptance Criteria

1. WHEN 用户执行 `python3 tools/weekly_summary/summarize.py` 且不带任何参数，THE Weekly_Summary_CLI SHALL 依次执行：加载默认配置、界定本周 Week_Window、采集 Git 与 Codex 数据、聚合、渲染并写入 `dev_log/<Report_Identifier>.md`。
2. WHEN 整个生成流程成功完成，THE Weekly_Summary_CLI SHALL 以零退出码（exit code 0）结束。
3. IF 生成流程因不可恢复的错误中止，THEN THE Weekly_Summary_CLI SHALL 以非零退出码结束，并向用户输出错误原因。

### Requirement 12: 可视化前端登录与访问控制

**User Story:** 作为在自有服务器上托管展示页的开发者，我希望前端通过 GitHub OAuth 登录并限定授权账户，以便只有我（或允许名单内的授权者）能访问「我学到了什么」。

> 安全提示：Visualization_Frontend 暴露于网络，缺少认证将导致周报数据（含项目名、提交标题、主题）公开可访问。本需求要求登录保护必须存在，且仅允许 Allow_List 内的 GitHub 账户访问。

#### Acceptance Criteria

1. WHILE 用户未通过认证，THE Auth_Service SHALL 阻止访问展示页面内容，并将请求重定向至 GitHub OAuth 2.0 授权码流程（authorization code flow）的登录入口。
2. WHEN GitHub 返回针对 Allow_List 内账户的成功 OAuth 回调，THE Auth_Service SHALL 完成令牌交换、建立服务端会话，并授予对展示页面的访问权限。
3. IF 已通过 GitHub 认证的账户不在 Allow_List 内，THEN THE Auth_Service SHALL 拒绝访问并返回「该账户无访问权限」提示，且不建立已认证会话。
4. IF GitHub OAuth 流程返回错误或用户拒绝授权（denied consent），THEN THE Auth_Service SHALL 终止登录、返回一条描述性认证失败提示，并将用户保持在未认证状态。
5. THE Auth_Service SHALL 通过加密传输通道（HTTPS）传输登录凭证与 OAuth 回调数据。

### Requirement 13: 可视化前端数据消费与展示

**User Story:** 作为开发者，我希望前端以美观、设计感强的方式呈现周报，以便愉快地回顾「我学到了什么」。

#### Acceptance Criteria

1. THE Visualization_Frontend SHALL 从挂载的数据目录中读取 CLI 生成的 JSON Structured_Export 文件（`<Report_Identifier>.json`）作为展示数据源，且不解析 Markdown。
2. WHEN 已认证用户打开展示页，THE Visualization_Frontend SHALL 展示所选周的时间分布、本周 commit、关键问题与汇总数字。
3. WHERE 存在多周的周报数据，THE Visualization_Frontend SHALL 提供按周切换查看的入口。
4. IF 请求的某一周不存在对应周报数据，THEN THE Visualization_Frontend SHALL 展示一条「该周暂无数据」的提示。

### Requirement 14: 可选飞书（Lark）集成

**User Story:** 作为使用飞书的开发者，我希望可选地通过自定义机器人 Webhook 把周报推送到飞书，以便在团队协作工具中查看。

#### Acceptance Criteria

1. WHERE 飞书集成在配置中被显式开启，THE Feishu_Integration SHALL 在周报生成完成后，向 `weekly-summary.toml` 中配置的自定义机器人 incoming webhook URL 发起一次单向推送（CLI → 飞书），推送周报内容。
2. IF 飞书 Webhook 推送失败，THEN THE Feishu_Integration SHALL 记录失败原因，且不影响本地周报文件的生成结果。
3. THE Weekly_Summary_CLI SHALL 使本地周报文件的生成完全独立于飞书推送，无论飞书推送成功、失败或被关闭。
4. WHILE 飞书集成处于关闭状态，THE Weekly_Summary_CLI SHALL 不向飞书发起任何请求。

### Requirement 15: 前端容器化打包与部署

**User Story:** 作为在自有服务器上托管展示页的开发者，我希望前端及其后端以 Docker 容器形式打包，以便在我自己的服务器上一键部署并从挂载目录读取周报数据。

#### Acceptance Criteria

1. THE Visualization_Frontend SHALL 与其 Next.js 后端一同打包为可在用户自有服务器上运行的 Docker 容器（提供 Dockerfile 与 docker-compose 配置）。
2. WHEN 容器启动，THE Visualization_Frontend SHALL 从挂载的数据卷/目录读取 JSON Structured_Export 文件作为周报数据源。
3. WHERE 数据目录通过数据卷挂载提供，THE Visualization_Frontend SHALL 在不重建镜像的前提下读取该目录中新增或更新的周报数据文件。
4. THE Visualization_Frontend SHALL 通过环境变量或挂载的配置接收运行所需参数（含 GitHub OAuth 客户端凭证与 Allow_List）。

## 设计阶段已确定的关键决策

以下决策点已在进入设计阶段前敲定，相关需求已据此细化：

1. **认证方式（Auth_Service）**：采用 GitHub OAuth 2.0 授权码流程，建立服务端会话，仅授权 Allow_List 内的 GitHub 账户（默认仅拥有者本人）。详见 Requirement 12。
2. **托管与部署**：以 Docker 容器（或 docker-compose）部署在用户自有服务器，前端及其后端一同打包，从挂载的数据卷读取周报数据。详见 Requirement 15。
3. **前端技术栈**：Next.js + Tailwind CSS，经 Docker 容器化；Next.js 承载 GitHub OAuth 令牌交换与会话 Cookie，并服务「类似 Apple 官网」审美的静态界面。视觉实现遵循「Claude Design 生成 mockup → 转 Next.js 前端」的流程：先产出设计稿，再实现。
4. **CLI 与前端的数据契约（Structured_Export）**：CLI 的 Data_Exporter 在 `dev_log/` 旁写出 JSON 文件（`dev_log/data/<Report_Identifier>.json`）；前端消费 JSON（不解析 Markdown）。用户通过 git push 或 rsync 将数据目录同步到服务器，容器从挂载的数据目录读取。详见 Requirement 10 与 13。
5. **飞书（Lark）集成形态**：采用自定义机器人 Webhook（在 `weekly-summary.toml` 中配置 incoming webhook URL），单向推送（CLI → 飞书）。详见 Requirement 14。
6. **Codex 会话日志格式**：路径为 `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<uuid>.jsonl`（JSONL，每行一个 JSON 对象）；首行 `type == "session_meta"`，`payload.cwd` 为项目目录、`payload.git` 含 commit/branch/repository_url；真实 User_Prompt 为 `type == "response_item"` 且 `payload.role == "user"`、`payload.type == "message"`、含 `input_text` 的行，须排除被 `<environment_context>` 等标签包裹的注入上下文消息。详见 Requirement 3。
