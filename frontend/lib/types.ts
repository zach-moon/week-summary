// frontend/lib/types.ts
//
// Structured_Export JSON 数据契约的 TypeScript 镜像（LOCAL tier 与 SERVER tier
// 之间唯一的跨层数据契约，Req 10.3 / 13.1）。
//
// ⚠️ 必须与 Python Data_Exporter 的 *实际输出* 保持同步：
//     tools/weekly_summary/export.py（`to_dict`）。
// 任何字段名 / 类型 / 可空性的改动都必须同时更新两侧，并按需递增
// `schema_version`（export.py 中的 SCHEMA_VERSION）。
//
// 注意（相对 design.md 旧示例的增量）：export.py 的 `to_dict` 在每个
// `repo_commits` 条目中追加了 `repo_path` 字段以保证无损 round-trip。
// 因此 RepoCommitGroup 在此处包含 `repo_path`，以镜像导出器的真实输出。

/** 顶层 Structured_Export 对象（`dev_log/data/<Report_Identifier>.json`）。 */
export interface StructuredExport {
  /** 契约版本号，前端按版本兼容处理（export.py: SCHEMA_VERSION）。 */
  schema_version: number;
  /** 周报标识，形如 "2026-W22"（Req 4.3）。 */
  report_identifier: string;
  /** 周起始日期，ISO date 字符串 "YYYY-MM-DD"。 */
  week_start: string;
  /** 周结束日期，ISO date 字符串 "YYYY-MM-DD"。 */
  week_end: string;
  /** 时间分布，已降序，含零活动项目（Req 5）。 */
  distribution: ProjectDistribution[];
  /** 各仓库 commit 列表（Req 6.3, 10.3）。 */
  repo_commits: RepoCommitGroup[];
  /** 各项目 codex 主题 / 关键问题摘要（Req 6.4, 10.3）。 */
  repo_codex: RepoCodexGroup[];
  /** 汇总数字（Req 6.5, 10.3）。 */
  numbers: {
    total_commits: number;
    total_sessions: number;
    total_user_prompts: number;
  };
  /** LLM 自动建议；关闭时为 null（Req 6.6 / 6.7）。 */
  llm_suggestions: string | null;
}

/** 单个项目目录的时间分布条目（Req 5.1, 5.2）。 */
export interface ProjectDistribution {
  /** 项目目录绝对路径。 */
  project_dir: string;
  /** basename，前端展示用（export.py 派生字段 `_basename`）。 */
  project_name: string;
  /** 窗内提交数，integer >= 0。 */
  commit_count: number;
  /** 窗内会话数，integer >= 0。 */
  session_count: number;
}

/** 单个仓库在时间窗内的 commit 分组（Req 6.3, 10.3）。 */
export interface RepoCommitGroup {
  /** 仓库标识。 */
  repo_id: string;
  /** 仓库路径；export.py 增量字段，保证无损 round-trip。 */
  repo_path: string;
  /** 时间窗内的提交（可能为空）。 */
  commits: { date: string; subject: string }[];
}

/** 单个项目的 codex 会话摘要分组（Req 6.4, 10.3）。 */
export interface RepoCodexGroup {
  /** 分组键（export.py 以 project_dir 作为 repo_id）。 */
  repo_id: string;
  /** 该组会话数。 */
  session_count: number;
  /** 摘要化主题关键词。 */
  themes: string[];
  /** 摘要化关键问题。 */
  key_questions: string[];
}
