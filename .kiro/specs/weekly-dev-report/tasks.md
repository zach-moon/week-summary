# Implementation Plan: 开发周报自动生成（weekly-dev-report）

## Overview

本实现计划把设计拆解为可增量交付的编码任务。整体顺序遵循「先打通 LOCAL tier 的 CLI 数据管线、再接可选能力、再做编排、最后做 SERVER tier 前端与容器打包」：

1. **CLI 数据管线**：`models.py` → `config.py` → `week_window.py` → `collectors/` → `aggregate.py` → `render.py` → `export.py`。这一段完成后即可独立运行与测试（采集、聚合、渲染、JSON 导出）。
2. **可选能力**：`llm.py`（默认关闭，隐私边界）、`feishu.py`（单向推送，与本地产出解耦）。
3. **编排层**：`summarize.py`（CLI 入口、覆盖确认、退出码、rsync over SSH 推送），把上述组件接线为端到端流程。
4. **SERVER tier 前端**：先落地 `lib/types.ts` 数据契约（与 `export.py` 保持同步），再做 `lib/data.ts`、认证、页面与组件，最后实现 Apple 审美样式。
5. **容器打包**：`next.config.js`（standalone）、`Dockerfile`、`docker-compose.yml`。

测试策略采用双轨：19 条 Correctness Properties 各由一个属性测试实现（Python 侧用 **Hypothesis** 覆盖 P1–P17，前端用 **fast-check** 覆盖 P18–P19），并辅以单元 / 集成 / 快照测试。属性测试与单元测试均以 `*` 标注为可选子任务。

> 约定：属性测试每条放在独立测试文件中，并以注释 `# Feature: weekly-dev-report, Property {n}: {text}` 标注；每个属性测试至少运行 100 次随机迭代（Hypothesis `max_examples>=100` / fast-check `numRuns>=100`）。

## Tasks

- [x] 1. 搭建 CLI 项目结构与核心数据模型
  - [x] 1.1 创建 `tools/weekly_summary/` 目录骨架、数据模型与测试框架
    - 创建目录结构：`tools/weekly_summary/`、`collectors/`、`templates/`、`tests/`
    - 在 `models.py` 中定义全部 dataclass：`Commit`、`RepoCommits`、`CodexSession`、`ProjectDistribution`、`AggregatedReport`、`Config`、`WeekWindow`、`LLMConfig`、`FeishuConfig`（按设计 Components 与 Data Models 章节的字段与类型注解）
    - 配置 `pytest` + `Hypothesis` 测试运行环境（`tests/` 包、配置文件、依赖声明）
    - _Requirements: 1.2, 2.2, 3.7, 4.3, 5.1, 5.2, 10.3_

- [x] 2. 实现配置加载 Config_Loader（`config.py`）
  - [x] 2.1 实现 `load_config` 与配置数据结构
    - 实现 `load_config(path)`：`path=None` 时读取 `DEFAULT_CONFIG_PATH`（`~/.config/weekly-summary.toml`）；解析 TOML 为 `Config`（含 `repos`、`output_dir`、`author`、`export_enabled`、`push_target`、`llm`、`feishu`）
    - 文件缺失抛 `ConfigMissingError`（消息含期望绝对路径）；TOML 语法非法抛 `ConfigParseError`（消息含行号/键名）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 2.2 创建默认配置模板 `templates/weekly-summary.toml`
    - 模板含仓库列表、`output_dir`、`author`、`export_enabled`、`push_target` 与 `[llm]`/`[feishu]` 段；`llm.enabled` 默认 `false`
    - _Requirements: 1.6, 8.2_
  - [ ]* 2.3 为配置解析编写属性测试
    - **Property 1: 配置解析正确性**（Hypothesis）
    - **Validates: Requirements 1.2**
  - [ ]* 2.4 为 LLM 配置持久性编写属性测试
    - **Property 15: LLM 配置持久性**（Hypothesis）——重复加载/读取后 `llm.enabled` 不被重置或修改
    - **Validates: Requirements 8.3**
  - [ ]* 2.5 编写配置加载单元测试
    - 默认路径选择（1.1）、`output_dir` 使用（1.5）、非法 TOML 报错含行号/键名（1.4）、默认模板 LLM 关闭（1.6/8.2）
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 8.2_

- [x] 3. 实现时间窗 Week_Window（`week_window.py`）
  - [x] 3.1 实现时间窗与周报标识计算
    - `current_week_window(now)`：`start` = 本周一 00:00:00（本地时区），`end` = `now`
    - `week_window_for(year, iso_week)`：周一 00:00:00 ~ 周日 23:59:59（本地时区）
    - `report_identifier(d)`：依据 ISO 8601 `isocalendar()` 产出 `YYYY-Www`（周序号两位补零），正确处理跨年周
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ]* 3.2 为默认时间窗编写属性测试
    - **Property 7: 默认 Week_Window 计算**（Hypothesis）
    - **Validates: Requirements 4.1**
  - [ ]* 3.3 为指定周时间窗编写属性测试
    - **Property 8: 指定周 Week_Window 计算**（Hypothesis）
    - **Validates: Requirements 4.2**
  - [ ]* 3.4 为周报标识编写属性测试
    - **Property 9: Report_Identifier 的 ISO 计算**（Hypothesis）
    - **Validates: Requirements 4.3**

- [x] 4. 实现 Git_Collector（`collectors/git_collector.py`）
  - [x] 4.1 实现 `collect_commits`
    - 对每个仓库执行时间窗内 `git -C <repo> log --since --until --pretty=format:%H%x1f%ad%x1f%s --date=short`，解析为 `Commit`（保留 `repo_id`/`date`/`subject`）
    - 支持 `--author` 作者过滤；非 git 路径捕获错误并产出标识该路径的 `Warning` 后继续；窗内无提交返回空 `commits`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [ ]* 4.2 为 Git 采集时间窗与字段保留编写属性测试
    - **Property 2: Git 采集落在时间窗内且保留字段**（Hypothesis）
    - **Validates: Requirements 2.1, 2.2**
  - [ ]* 4.3 为作者过滤编写属性测试
    - **Property 3: Git 作者过滤**（Hypothesis）
    - **Validates: Requirements 2.4**
  - [ ]* 4.4 编写 Git_Collector 单元测试
    - 非 git 路径告警并继续（2.3）、窗内空提交返回空集合（2.5）
    - _Requirements: 2.3, 2.5_

- [x] 5. 实现 Codex_Collector（`collectors/codex_collector.py`）
  - [x] 5.1 实现 `collect_sessions`、JSONL 解析与注入消息排除
    - 遍历 `~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl`；首行 `session_meta` 取 `payload.cwd` → `project_dir`、`payload.timestamp` → `date`
    - 提取真实 User_Prompt：`type=="response_item"` 且 `payload.type=="message"`、`payload.role=="user"`、含 `input_text` 的行
    - 实现 `is_injected(text)`：`lstrip()` 后以 `INJECTED_TAGS`（`<environment_context>` 等）前缀开头则排除，不计入 `user_prompts` 与 `prompt_count`
    - 单文件解析失败跳过 + 告警 + 继续；`~/.codex/sessions/` 不存在返回空集合 + 信息
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [ ]* 5.2 为 Codex 会话解析正确性编写属性测试
    - **Property 4: Codex 会话解析正确性**（Hypothesis）
    - **Validates: Requirements 3.2, 3.3, 3.7**
  - [ ]* 5.3 为注入上下文消息排除编写属性测试
    - **Property 5: 注入上下文消息被排除（关键）**（Hypothesis）
    - **Validates: Requirements 3.4**
  - [ ]* 5.4 为会话文件发现与时间过滤编写属性测试
    - **Property 6: Codex 会话文件发现与时间过滤**（Hypothesis）
    - **Validates: Requirements 3.1**
  - [ ]* 5.5 用真实 Codex JSONL fixtures 编写单元测试
    - 真实样例验证解析与注入排除（含 `<environment_context>` 等包裹消息）、损坏文件跳过（3.5）、目录缺失（3.6）
    - _Requirements: 3.4, 3.5, 3.6_

- [x] 6. Checkpoint — 采集与基础组件测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 实现 Report_Aggregator（`aggregate.py`）
  - [x] 7.1 实现 `aggregate`
    - 为配置中每个项目目录建 `ProjectDistribution` 条目（含 commit/session 均为零的项目）
    - 项目归属：git 提交按仓库 `path` 入桶；Codex 会话 `cwd` 与各仓库 `path` 做路径归一化后**最长前缀匹配**；未匹配归入 `__unmatched__`
    - 计算各项目 `commit_count`/`session_count` 与汇总 `total_*`；`distribution` 按 `(commit_count, session_count)` 降序排序
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ]* 7.2 为聚合建条目与计数编写属性测试
    - **Property 10: 聚合为每个项目建条目且计数正确**（Hypothesis）
    - **Validates: Requirements 5.1, 5.2**
  - [ ]* 7.3 为聚合排序不变式编写属性测试
    - **Property 11: 聚合排序不变式**（Hypothesis）
    - **Validates: Requirements 5.3**

- [x] 8. 实现 Markdown_Renderer（`render.py`）
  - [x] 8.1 实现 `render_markdown`
    - 生成中文 Markdown：标题含 `report_identifier` 与起止日期（`YYYY-MM-DD`）；固定章节「时间分布」「本周做了什么（commit）」「我提了什么关键问题（codex）」「数字」
    - 「自动建议（可选，LLM）」章节仅当 `report.llm_suggestions is not None` 时渲染，其余章节始终生成
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  - [ ]* 8.2 为渲染包含性编写属性测试
    - **Property 12: Markdown 渲染包含性**（Hypothesis）
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
  - [ ]* 8.3 为 LLM 章节条件渲染编写属性测试
    - **Property 13: LLM 建议章节的条件渲染**（Hypothesis）
    - **Validates: Requirements 6.6, 6.7**

- [ ] 9. 实现 Data_Exporter（`export.py`，跨层数据契约）
  - [x] 9.1 实现 `to_dict` / `from_dict` / `export_json`
    - 按 Structured_Export JSON schema 序列化 `AggregatedReport`（`schema_version`、`report_identifier`、起止日期、`distribution`、`repo_commits`、`repo_codex` 仅含 `themes`/`key_questions`、`numbers`、`llm_suggestions`）
    - 写入 `dev_log/data/<Report_Identifier>.json`，目录不存在则创建并返回写入路径
    - `from_dict` 遇损坏/缺字段 JSON 抛 `ExportFormatError`（描述性）
    - _Requirements: 10.1, 10.2, 10.3, 10.5_
  - [ ]* 9.2 为 JSON 序列化 round-trip 编写属性测试
    - **Property 17: JSON 序列化 round-trip 等价**（Hypothesis）
    - **Validates: Requirements 10.3, 10.4**
  - [ ]* 9.3 编写 Data_Exporter 单元测试
    - 落地路径（10.1）、目录创建（10.2）、损坏 JSON 报错（10.5）
    - _Requirements: 10.1, 10.2, 10.5_

- [x] 10. Checkpoint — CLI 数据管线可独立端到端运行
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 实现 LLM_Narrator（`llm.py`，可选，默认关闭）
  - [x] 11.1 实现 `build_llm_input` / `narrate` / `LLMInput`
    - `build_llm_input` 仅构造摘要要点（`project_names`、`topic_keywords`、`commit_subjects`），从类型层面排除原始 transcript
    - `narrate` 在开启且有凭证时生成主题归纳与下周建议；API key 仅从环境变量 `WEEKLY_SUMMARY_LLM_API_KEY` 读取
    - 调用失败返回 `None` 并记录、继续生成；缺凭证返回缺凭证错误信息并生成无 LLM 章节周报
    - _Requirements: 8.5, 8.6, 9.1, 9.2, 9.3_
  - [ ]* 11.2 为 LLM 外发摘要边界编写属性测试
    - **Property 16: LLM 开启时仅外发摘要且不含原始对话**（Hypothesis）——任一 `user_prompt` 原文都不是外发负载的子串
    - **Validates: Requirements 8.5, 8.6**
  - [ ]* 11.3 编写 LLM_Narrator 单元测试
    - 调用失败降级（9.2）、缺 API 凭证（9.3）
    - _Requirements: 9.2, 9.3_

- [x] 12. 实现 Feishu_Integration（`feishu.py`，可选）
  - [x] 12.1 实现 `push_to_feishu`
    - 开启时向自定义机器人 incoming webhook 做一次单向推送；推送失败记录原因且不影响本地 `.md`/`.json` 产出；关闭时不发起任何请求；webhook URL 视为机密（可由环境变量覆盖）
    - _Requirements: 14.1, 14.2, 14.3, 14.4_
  - [ ]* 12.2 编写 Feishu_Integration 单元测试
    - 关闭时零调用（14.4）、推送成功/失败/关闭三态下本地产出一致（14.2/14.3）、开启时推送一次（14.1，mock webhook）
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

- [x] 13. 实现 summarize.py（编排层 / CLI 入口）
  - [x] 13.1 实现 `main` 与端到端编排
    - 解析 CLI 参数 `--config`/`--week`/`--output-dir`/`--push`/`--yes`；按默认流程接线：`load_config` → 时间窗 → `collect_commits`+`collect_sessions` → `aggregate` →（可选 `narrate`）→ `render_markdown` → 写 `dev_log/<id>.md` →（可选 `export_json`）→（可选 `push_to_feishu`）
    - 覆盖逻辑：不存在直接写（7.4）；交互式（`isatty`）展示确认（7.3）；非交互式跳过覆盖并提示（7.5）；写入后打印绝对路径（7.6）；输出目录不存在则创建（7.2）；写入 `dev_log/<Report_Identifier>.md`（7.1）
    - `--push` 且配置含 `push_target` 时，在导出 JSON 后执行 `rsync -az --delete-after dev_log/data/ "$push_target"`（rsync over SSH，复用既有密钥互信）
    - 成功退出码 0（11.2）；不可恢复错误非零退出并打印原因（11.3）
    - _Requirements: 11.1, 11.2, 11.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 4.1, 4.2_
  - [ ]* 13.2 为 LLM 关闭时零外发编写属性测试
    - **Property 14: LLM 关闭时全流程零外发**（Hypothesis）——`llm.enabled==false` 时跑完整流程，外部网络层记录零次调用
    - **Validates: Requirements 8.1, 8.4**
  - [ ]* 13.3 编写编排层单元测试
    - 交互式覆盖确认（7.3/7.4）、非交互式跳过（7.5）、打印绝对路径（7.6）、成功退出码（11.2）、不可恢复错误退出码（11.3）
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 11.2, 11.3_
  - [ ]* 13.4 编写端到端 CLI 集成测试
    - 用 fixtures 仓库 + codex 日志跑完整默认流程，断言生成 `.md` 与 `.json`
    - _Requirements: 11.1_

- [x] 14. Checkpoint — CLI 全流程（含可选能力与编排）测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. 搭建前端脚手架与数据契约（types 优先，保持与 export.py 同步）
  - [x] 15.1 创建 `frontend/` Next.js + Tailwind 脚手架与 `lib/types.ts`
    - 初始化 App Router 工程（`package.json`、`tsconfig`、Tailwind 配置、`app/layout.tsx`）
    - 在 `lib/types.ts` 中定义 `StructuredExport`、`ProjectDistribution`、`RepoCommitGroup`、`RepoCodexGroup`，字段名与类型逐一镜像 `export.py` 的 JSON 契约
    - _Requirements: 13.1, 10.3_
  - [x] 15.2 实现 `lib/data.ts`
    - `listAvailableWeeks()`：扫描 `DATA_DIR`（默认 `/data`）下 `*.json` 返回 Report_Identifier 列表（每次请求扫描，新增文件无需重建镜像）
    - `loadReport(id)`：读取 `<id>.json`，不存在返回 `null`；仅在服务端读取，只读 JSON 不解析 Markdown
    - _Requirements: 13.1, 13.3, 13.4, 15.2, 15.3_
  - [ ]* 15.3 为前端 loader 与 CLI 导出契约一致编写属性测试
    - **Property 18: 前端 loader 与 CLI 导出契约一致**（fast-check）——对合法 Structured_Export，`loadReport` 解析结构与导出结构等价
    - **Validates: Requirements 13.1**
  - [ ]* 15.4 为 `listAvailableWeeks` 编写 fast-check 属性测试
    - 对任意一组 `<id>.json` 文件名集合，`listWeeks` 应恰好返回对应的 Report_Identifier 集合（仅 `*.json`，去除扩展名）
    - _Requirements: 13.3, 15.3_

- [x] 16. 实现前端认证 Auth_Service（GitHub OAuth + Allow_List）
  - [x] 16.1 实现 `lib/auth.ts`、`app/api/auth/[...nextauth]/route.ts` 与 `middleware.ts`
    - 配置 NextAuth v5 GitHub provider（`clientId`/`clientSecret` 来自环境变量）；`signIn` 回调用 `Allow_List`（环境变量 `ALLOW_LIST`，逗号分隔、小写归一）校验，不在名单返回 `false`
    - 设置 `pages: { signIn: "/login", error: "/unauthorized" }`；`middleware.ts` 保护除 `api/auth`/`login`/`unauthorized` 外的所有路由；OAuth 回调使用 HTTPS、会话 cookie `secure`/`httpOnly`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 15.4_
  - [ ]* 16.2 为 Allow_List 校验编写 fast-check 属性测试
    - **Property 19: Allow_List 校验**（fast-check）——`signIn` 返回 `true` 当且仅当 `login`（不区分大小写）属于名单
    - **Validates: Requirements 12.3**
  - [ ]* 16.3 编写认证集成测试
    - mock OAuth profile：未认证重定向登录入口（12.1）、名单内成功建立会话（12.2）、OAuth 错误/拒绝授权保持未认证（12.4）
    - _Requirements: 12.1, 12.2, 12.4_

- [x] 17. 实现前端页面与展示组件
  - [x] 17.1 实现展示组件
    - 组件：时间分布、commit 列表、codex 关键问题、汇总数字、周切换器（week switcher）、无数据空态
    - 组件消费 `lib/types.ts` 的 `StructuredExport`
    - _Requirements: 13.2, 13.3, 13.4_
  - [x] 17.2 实现页面路由
    - `app/page.tsx`（仪表盘，默认最新周）、`app/week/[id]/page.tsx`（指定周）、`app/login/page.tsx`（GitHub 登录入口）、`app/unauthorized/page.tsx`（无访问权限提示）
    - 服务端通过 `lib/data.ts` 读取数据并装配组件；请求周无数据展示「该周暂无数据」
    - _Requirements: 13.2, 13.3, 13.4, 12.3, 12.4_
  - [ ]* 17.3 编写组件 / 快照测试
    - 仪表盘渲染四区块（13.2）、多周下周切换入口出现（13.3）、无数据提示（13.4）
    - _Requirements: 13.2, 13.3, 13.4_

- [ ] 18. 实现 Apple 审美样式（Tailwind 视觉层）
  - [ ] 18.1 依据 Claude Design mockup 落地视觉样式
    - **依赖外部输入**：本任务需等用户提供 Claude Design 生成的设计稿 mockup 后再实现；在此之前页面/组件以基础样式占位
    - 按 mockup 落地 typography、留白、低调动效与色彩 token，应用到既有页面与组件（Tailwind）
    - _Requirements: 13.2_

- [x] 19. Checkpoint — 前端测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 20. 前端容器化打包
  - [x] 20.1 实现 `next.config.js`、`Dockerfile` 与 `docker-compose.yml`
    - `next.config.js` 设 `output: "standalone"`；`Dockerfile` 多阶段构建（deps/build/runner，复制 `.next/standalone`+`.next/static`+`public`，非 root 运行）
    - `docker-compose.yml`：只读挂载 `/data` 数据卷，经环境变量注入 `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`/`AUTH_SECRET`/`ALLOW_LIST`/`AUTH_URL`/`DATA_DIR`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 12.5_
  - [ ]* 20.2 编写容器与挂载集成/冒烟测试
    - 镜像构建成功、挂载样例数据卷读取（15.2）、运行中新增 JSON 无需重建即可读（15.3）
    - _Requirements: 15.1, 15.2, 15.3_

- [ ] 21. Final checkpoint — 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标注 `*` 的子任务为可选（单元测试、属性测试、集成/快照测试），可为快速 MVP 跳过；核心实现任务不可跳过。
- 每个任务引用了具体的需求子条款以保证可追溯。
- 19 条 Correctness Properties 与属性测试一一对应：P1（2.3）、P2/P3（4.2/4.3）、P4/P5/P6（5.2/5.3/5.4）、P7/P8/P9（3.2/3.3/3.4）、P10/P11（7.2/7.3）、P12/P13（8.2/8.3）、P14（13.2）、P15（2.4）、P16（11.2）、P17（9.2）、P18（15.3）、P19（16.2）。
- Property 17（round-trip）与 Property 4/5（解析与注入排除）为最高优先级属性测试。
- Checkpoint 用于在关键节点做增量校验。
- Task 18.1（Apple 审美样式）依赖用户提供的 Claude Design mockup 这一外部输入，已在任务中标注。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3.1", "4.1", "5.1"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.5", "3.2", "3.3", "3.4", "4.2", "4.3", "4.4", "5.2", "5.3", "5.4", "5.5", "7.1"] },
    { "id": 3, "tasks": ["7.2", "7.3", "8.1", "9.1"] },
    { "id": 4, "tasks": ["8.2", "8.3", "9.2", "9.3", "11.1", "12.1"] },
    { "id": 5, "tasks": ["11.2", "11.3", "12.2", "13.1"] },
    { "id": 6, "tasks": ["13.2", "13.3", "13.4", "15.1"] },
    { "id": 7, "tasks": ["15.2", "16.1"] },
    { "id": 8, "tasks": ["15.3", "15.4", "16.2", "16.3", "17.1"] },
    { "id": 9, "tasks": ["17.2"] },
    { "id": 10, "tasks": ["17.3"] },
    { "id": 11, "tasks": ["18.1", "20.1"] },
    { "id": 12, "tasks": ["20.2"] }
  ]
}
```
