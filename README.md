# 开发周报自动生成（weekly-dev-report）

在周末花约 5 分钟，自动总结「本周做了什么」。

`git log` 只能告诉你**改了哪些文件**，却说不清**为什么改**；而 Codex CLI 的会话记录
保留了思考过程（在想什么、在学什么、卡在哪里）。本工具把这两类数据源合并，生成一份
真正可回顾的中文复盘——即使 6 个月后再看也能看懂。

## 架构概览

项目由两个**部署层级（deployment tier）**组成，通过一份**摘要化的 JSON 数据契约**解耦：

| 层级 | 组件 | 运行位置 | 职责 |
| --- | --- | --- | --- |
| **LOCAL tier** | `tools/weekly_summary/`（Python CLI） | 开发者本机 | 采集 `git log` + `~/.codex/sessions/`、按项目聚合、渲染中文 Markdown、导出结构化 JSON |
| **SERVER tier** | `frontend/`（Next.js + Tailwind，Docker） | 自有服务器 | 只读消费摘要 JSON，提供 GitHub OAuth 登录 + Allow_List 访问控制与可视化展示 |

两层之间唯一的数据流是 **HANDOFF**：仅把摘要化的 JSON（`dev_log/data/<id>.json`）
从本地同步到服务器，默认机制为 **rsync over SSH**。

### 隐私边界（第一性约束）

- 采集与摘要**只在本地发生**；原始 git diff、源代码、Codex 原始对话内容绝不离开本地。
- 跨越边界的只有**摘要数据**：项目名、commit 标题、主题关键词、各类计数。
- **LLM 调用默认关闭**；即使开启，也只发送摘要化结构化要点，绝不发送原始对话。
- SERVER tier 暴露在网络上，因此强制要求 GitHub OAuth + Allow_List。
- 所有密钥（OAuth secret、飞书 webhook、LLM API key）经环境变量提供，绝不入库。

```
LOCAL tier（隐私边界内）                         SERVER tier（网络暴露）
┌─────────────────────────────────┐            ┌──────────────────────────┐
│ git 仓库 ┐                       │            │  挂载数据卷 /data/*.json  │
│ ~/.codex ┼─► Weekly_Summary_CLI  │  rsync     │         │                │
│ config   ┘   ├ collect/aggregate │ ═════════► │  Next.js + Auth.js       │
│              ├ render → .md      │  仅摘要JSON │   ├ GitHub OAuth+Allow   │
│              └ export → .json ───┼────────────┤   ├ 读取 JSON            │
│                                  │            │   └ Apple 审美仪表盘     │
└─────────────────────────────────┘            └──────────────────────────┘
```

## LOCAL tier — Weekly_Summary_CLI

### 依赖

- Python 3.11+（使用标准库 `tomllib`；无第三方运行时依赖）
- `git`（用于采集提交记录）
- 开发依赖：`pytest`、`hypothesis`（仅测试需要）

### 快速开始

```bash
# 1) 准备配置文件（默认路径 ~/.config/weekly-summary.toml）
cp tools/weekly_summary/templates/weekly-summary.toml ~/.config/weekly-summary.toml
# 编辑 repos / author / output_dir 等字段

# 2) 生成本周周报（无参数即默认本周）
python3 tools/weekly_summary/summarize.py
```

成功后会在 `dev_log/<YYYY>-W<week>.md` 写入中文 Markdown 周报，并（默认开启时）
在 `dev_log/data/<YYYY>-W<week>.json` 写入结构化数据；终端打印产出文件的绝对路径。

### 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--config <path>` | 配置文件路径；省略时使用 `~/.config/weekly-summary.toml` |
| `--week <YYYY-Www>` | 目标周（如 `2026-W22`）；省略时默认本周 |
| `--output-dir <dir>` | 输出目录；覆盖配置中的 `output_dir`（默认 `dev_log`） |
| `--push` | 导出 JSON 后经 rsync over SSH 同步 `dev_log/data/` 到 `push_target` |
| `--yes` | 目标周报已存在时强制覆盖，不展示确认提示 |

### 配置（`weekly-summary.toml`）

```toml
repos = [
    "/Users/me/Projects/project-a",
    "/Users/me/Projects/project-b",
]
output_dir = "dev_log"
author = "me@example.com"     # 仅采集该作者的提交；留空表示不过滤
export_enabled = true          # 是否导出结构化 JSON（供前端消费）
push_target = "user@server:/srv/weekly/data/"   # rsync 远端目标；留空表示不推送

[llm]
enabled = false                # 默认关闭（隐私优先）
provider = "openai"
model = "gpt-4o-mini"
# API key 经环境变量 WEEKLY_SUMMARY_LLM_API_KEY 提供

[feishu]
enabled = false
# webhook_url 建议经环境变量 WEEKLY_SUMMARY_FEISHU_WEBHOOK 提供（视为机密）
webhook_url = ""
```

### 数据交接（HANDOFF）

数据交接默认采用 **rsync over SSH**，复用既有 SSH 密钥互信：

```bash
# 配置 push_target 后运行
python3 tools/weekly_summary/summarize.py --push
# 等价于：rsync -az --delete-after dev_log/data/ "$push_target"
```

### 模块结构

```
tools/weekly_summary/
├── summarize.py          # CLI 入口 / 编排层
├── config.py             # 配置加载（TOML）
├── week_window.py        # 时间窗与 Report_Identifier 计算
├── collectors/
│   ├── git_collector.py  # 跨仓库 git 提交采集
│   └── codex_collector.py# Codex 会话 JSONL 解析、注入消息排除
├── aggregate.py          # 按项目聚合与排序
├── render.py             # 中文 Markdown 渲染
├── export.py             # 结构化 JSON 序列化（跨层数据契约）
├── llm.py                # 可选 LLM 归纳（默认关闭）
├── feishu.py             # 可选飞书 webhook 推送
├── models.py             # 数据模型（dataclasses）
├── templates/            # 默认配置模板
└── tests/                # 单元 + 属性测试 + fixtures
```

## SERVER tier — Visualization_Frontend

Next.js（App Router）+ Tailwind CSS，以 Docker 容器形式部署在自有服务器，
从挂载的只读数据卷读取摘要 JSON 进行展示。

### 本地开发

```bash
cd frontend
npm install
# 必需环境变量见下表
DATA_DIR=../dev_log/data npm run dev
```

### 环境变量

| 变量 | 说明 |
| --- | --- |
| `DATA_DIR` | 摘要 JSON 目录（容器内默认 `/data`） |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth App 凭证 |
| `ALLOW_LIST` | 逗号分隔的 GitHub 登录名白名单（不区分大小写） |
| `AUTH_SECRET` | Auth.js 会话/JWT 加密密钥 |
| `AUTH_URL` | 站点 URL，生产必须为 `https://...`（OAuth 回调 + secure cookie） |

### 容器部署

```bash
cd frontend
# 经环境变量注入 secrets 后启动；数据卷以只读方式挂载到 /data
WEEKLY_DATA_DIR=/srv/weekly/data docker compose up -d --build
```

容器仅监听 HTTP:3000，对外 HTTPS 由前置反向代理（Nginx/Caddy）终止 TLS。
运行中新增/更新的 JSON 无需重建镜像即可被读取。

### 前端结构

```
frontend/
├── app/                  # App Router 页面（仪表盘 / 指定周 / 登录 / 无权限）
│   └── api/auth/[...nextauth]/  # Auth.js 路由
├── lib/
│   ├── auth.ts           # GitHub OAuth + Allow_List 校验
│   ├── data.ts           # 服务端读取/扫描数据目录
│   └── types.ts          # Structured_Export 数据契约（镜像 export.py）
├── components/           # 展示组件（时间分布/commit/codex/数字/周切换器）
├── middleware.ts         # 路由保护
├── Dockerfile            # standalone 多阶段构建
└── docker-compose.yml    # 只读数据卷 + 环境变量注入
```

## 测试

测试采用**双轨策略**：属性测试（PBT）覆盖通用正确性，单元/集成/快照测试覆盖具体示例
与边界。19 条 Correctness Properties 与属性测试一一对应。

```bash
# LOCAL tier（Python，Hypothesis）
.venv/bin/python -m pytest tools/weekly_summary/tests/ -q

# SERVER tier（前端，fast-check + vitest）
cd frontend && npm test
```

- Python 侧：Hypothesis 覆盖 Property 1–17（每条 ≥100 次随机迭代）。
- 前端侧：fast-check 覆盖 Property 18–19（loader↔CLI 契约一致、Allow_List 校验）。
- 可选的 Docker 构建冒烟测试默认跳过，设置 `RUN_DOCKER_SMOKE=1` 且 Docker 可用时执行。

## 规格文档

完整的需求、设计与任务拆解见 `.kiro/specs/weekly-dev-report/`：

- `requirements.md` — EARS 验收标准
- `design.md` — 架构、组件接口、数据契约、19 条 Correctness Properties
- `tasks.md` — 实现计划与任务依赖图
