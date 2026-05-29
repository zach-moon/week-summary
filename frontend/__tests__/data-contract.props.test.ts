// Feature: weekly-dev-report, Property 18: 前端 loader 与 CLI 导出契约一致
//
// Property 18（fast-check）—— 前端 loader 与 CLI 导出契约一致。
// **Validates: Requirements 13.1**
//
// 对任意「由 CLI Data_Exporter 导出的合法 Structured_Export JSON」，前端
// `loadReport` 解析出的对象应与导出时的结构等价（字段名与类型逐一对应），
// 从而保证 LOCAL tier（Python `export.py` `to_dict`）与 SERVER tier
// （`frontend/lib/data.ts` `loadReport`）之间的跨语言数据契约一致。
//
// 生成的 Structured_Export 严格镜像 `tools/weekly_summary/export.py` 的
// `to_dict` 输出 schema（字段名 / 类型 / 可空性），以及
// `frontend/lib/types.ts` 中 StructuredExport / ProjectDistribution /
// RepoCommitGroup（含增量字段 `repo_path`）/ RepoCodexGroup 的定义。
//
// ⚠️ 注意：`data.ts` 在模块加载时即捕获 `const DATA_DIR = process.env.DATA_DIR`，
// 因此必须在 import 之前设置好 `DATA_DIR`（指向一个稳定的临时基目录），
// 之后每次迭代仅在该目录下写入不同 `<id>.json` 并以对应 id 调用 loadReport。

import { mkdtempSync, rmSync, writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import fc from "fast-check";
import { afterAll, expect, test } from "vitest";

// 1) 先创建稳定的临时数据目录，并在 import loadReport 之前注入 DATA_DIR。
const ORIGINAL_DATA_DIR = process.env.DATA_DIR;
const BASE_DIR = mkdtempSync(path.join(tmpdir(), "wdr-contract-"));
process.env.DATA_DIR = BASE_DIR;

// 2) 动态 import：确保上面的 DATA_DIR 设置在 data.ts 模块求值之前生效。
const { loadReport } = await import("@/lib/data");

afterAll(() => {
  // 还原环境变量并清理临时目录。
  if (ORIGINAL_DATA_DIR === undefined) {
    delete process.env.DATA_DIR;
  } else {
    process.env.DATA_DIR = ORIGINAL_DATA_DIR;
  }
  rmSync(BASE_DIR, { recursive: true, force: true });
});

// --------------------------------------------------------------------------- //
// 生成器：智能约束到「合法 Structured_Export」的输入空间。
// 字段集合与类型与 export.py `to_dict` / types.ts 一一对应。
// --------------------------------------------------------------------------- //

/** 安全 Report_Identifier：匹配 data.ts 的 SAFE_ID = /^[A-Za-z0-9_-]+$/，非空。 */
const ID_CHARS =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-".split("");
const safeIdArb: fc.Arbitrary<string> = fc
  .array(fc.constantFrom(...ID_CHARS), { minLength: 1, maxLength: 24 })
  .map((chars) => chars.join(""));

/** ISO date 字符串 "YYYY-MM-DD"（与 export.py 的 date.isoformat() 对齐）。 */
const isoDateArb: fc.Arbitrary<string> = fc
  .date({ min: new Date("2000-01-01T00:00:00Z"), max: new Date("2100-01-01T00:00:00Z") })
  .map((d) => d.toISOString().slice(0, 10));

/** 非负整数计数（commit_count / session_count / numbers.* 等）。 */
const countArb: fc.Arbitrary<number> = fc.integer({ min: 0, max: 1_000_000 });

/** distribution 条目：{ project_dir, project_name, commit_count, session_count } */
const distributionItemArb = fc.record({
  project_dir: fc.string(),
  project_name: fc.string(),
  commit_count: countArb,
  session_count: countArb,
});

/** repo_commits 条目：{ repo_id, repo_path, commits: [{date, subject}] } */
const repoCommitGroupArb = fc.record({
  repo_id: fc.string(),
  repo_path: fc.string(),
  commits: fc.array(
    fc.record({
      date: isoDateArb,
      subject: fc.string(),
    }),
    { maxLength: 8 },
  ),
});

/** repo_codex 条目：{ repo_id, session_count, themes: string[], key_questions: string[] } */
const repoCodexGroupArb = fc.record({
  repo_id: fc.string(),
  session_count: countArb,
  themes: fc.array(fc.string(), { maxLength: 8 }),
  key_questions: fc.array(fc.string(), { maxLength: 8 }),
});

/** 顶层 Structured_Export 对象，镜像 export.py `to_dict` 的精确 schema。 */
const structuredExportArb = fc.record({
  schema_version: fc.integer({ min: 0, max: 1_000 }),
  report_identifier: safeIdArb,
  week_start: isoDateArb,
  week_end: isoDateArb,
  distribution: fc.array(distributionItemArb, { maxLength: 8 }),
  repo_commits: fc.array(repoCommitGroupArb, { maxLength: 8 }),
  repo_codex: fc.array(repoCodexGroupArb, { maxLength: 8 }),
  numbers: fc.record({
    total_commits: countArb,
    total_sessions: countArb,
    total_user_prompts: countArb,
  }),
  // llm_suggestions: string | null —— 镜像 export.py `_optional_str` 的可空性。
  llm_suggestions: fc.option(fc.string(), { nil: null }),
});

// --------------------------------------------------------------------------- //
// Property 18：契约等价（round-trip across the JSON / cross-language boundary）。
// --------------------------------------------------------------------------- //
test("Property 18: loadReport parses CLI-exported Structured_Export back to an equivalent object", async () => {
  await fc.assert(
    fc.asyncProperty(safeIdArb, structuredExportArb, async (id, exported) => {
      // CLI Data_Exporter 落盘形态：JSON.dump(to_dict(report)) 写入 <DATA_DIR>/<id>.json。
      const filePath = path.join(BASE_DIR, `${id}.json`);
      writeFileSync(filePath, JSON.stringify(exported), "utf8");

      try {
        const loaded = await loadReport(id);
        // 前端解析出的对象应与导出对象结构等价：字段名、类型与值在 JSON
        // 往返 / 跨语言契约下逐一保持一致。
        expect(loaded).toEqual(exported);
      } finally {
        unlinkSync(filePath);
      }
    }),
    { numRuns: 100 },
  );
});

// 附带断言：不存在的 id（ENOENT 路径）应返回 null（Req 13.4 空态），
// 不影响主契约属性，仅作为补充健壮性检查。
test("loadReport returns null for a non-existent report id (ENOENT path)", async () => {
  await expect(loadReport("definitely-missing-week-id")).resolves.toBeNull();
});
