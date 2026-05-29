// frontend/lib/data.ts
//
// Data Reader（SERVER tier）——服务端从挂载的数据卷读取摘要 JSON 并扫描可用周次。
// 对应 design.md「Data Reader (lib/data.ts)」与 Req 13.1 / 13.3 / 13.4 / 15.2 / 15.3。
//
// ⚠️ SERVER-ONLY 模块：本文件使用 Node 的 `fs/promises` 与 `path`，只能在
// Server Component / Route Handler / Server Action 等服务端环境中导入，
// **禁止**被 Client Component（`"use client"`）直接或间接引用，否则会在打包时报错
// 并可能向客户端泄露文件系统路径。
// （未引入 `server-only` 包以避免新增依赖；如后续安装该包，可在此处加
//  `import "server-only";` 以获得编译期保护。）

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

import type { StructuredExport } from "@/lib/types";

/**
 * 数据卷目录。容器以只读方式挂载摘要 JSON 到该路径（默认 `/data`，Req 15.2）。
 * 通过环境变量 `DATA_DIR` 覆盖，便于本地开发与测试。
 */
const DATA_DIR = process.env.DATA_DIR ?? "/data";

/**
 * 合法 Report_Identifier 模式。CLI 侧产出形如 `2026-W22`（`<ISO-year>-W<week>`），
 * 这里采用更宽松但安全的字符集：仅允许字母、数字、下划线与连字符。
 *
 * 该正则同时承担**路径穿越防护**职责：任何包含 `/`、`\\`、`..` 或其它路径分隔符
 * 的 id 都不会匹配，从而无法读取 `DATA_DIR` 之外的文件。
 */
const SAFE_ID = /^[A-Za-z0-9_-]+$/;

/** id 是否为安全的 Report_Identifier（防止路径穿越）。 */
function isSafeId(id: string): boolean {
  return typeof id === "string" && SAFE_ID.test(id);
}

/**
 * 扫描 `DATA_DIR` 下的 `*.json` 文件，返回 Report_Identifier 列表（去除 `.json` 扩展名）。
 *
 * - **每次请求都重新扫描目录**：新同步进来的周报 JSON 无需重建镜像即可被发现（Req 15.3）。
 * - 仅匹配以 `.json` 结尾的文件；忽略子目录与其它文件。
 * - 仅返回通过 {@link isSafeId} 校验的标识，避免异常文件名污染列表。
 * - 排序：**按标识降序**（descending）。Report_Identifier 形如 `YYYY-Www`，
 *   字典序降序即可让**最新的周排在最前**，方便仪表盘默认展示最新周。
 * - 目录不存在或读取失败（如尚未挂载数据卷）时返回空数组 `[]`，不抛错。
 *
 * Req: 13.3, 15.2, 15.3
 */
export async function listAvailableWeeks(): Promise<string[]> {
  let entries: import("node:fs").Dirent[];
  try {
    entries = await readdir(DATA_DIR, { withFileTypes: true });
  } catch {
    // 目录不存在 / 不可读（例如数据卷尚未挂载）——视为「无可用周次」。
    return [];
  }

  const ids = entries
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".json"))
    .map((entry) => entry.name.slice(0, -".json".length))
    .filter(isSafeId);

  // 降序排序：最新周（字典序更大的 YYYY-Www）排在最前。
  ids.sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  return ids;
}

/**
 * 读取 `<DATA_DIR>/<id>.json` 并解析为 {@link StructuredExport}。
 *
 * - **仅读取 JSON，从不解析 Markdown**（Req 13.1）；JSON 是稳定的跨层数据契约。
 * - 文件不存在（`ENOENT`）时返回 `null` → UI 展示「该周暂无数据」（Req 13.4）。
 * - **路径穿越防护**：`id` 必须匹配安全模式（见 {@link isSafeId}）；不安全的 id
 *   直接返回 `null`，绝不拼接到路径中读取 `DATA_DIR` 之外的文件。
 * - 文件存在但内容非法 JSON 时，向上抛出解析错误（由调用方决定如何处理），
 *   以区别于「文件不存在」这一正常空态。
 *
 * 仅在服务端调用（Server Component / Route Handler）。
 *
 * Req: 13.1, 13.4, 15.2
 */
export async function loadReport(id: string): Promise<StructuredExport | null> {
  if (!isSafeId(id)) {
    // 拒绝不安全 id（含 "/"、"\\"、".." 或路径分隔符等）——当作「无此周」处理。
    return null;
  }

  const filePath = path.join(DATA_DIR, `${id}.json`);
  let raw: string;
  try {
    raw = await readFile(filePath, "utf8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") {
      return null; // 文件不存在 → 该周暂无数据（Req 13.4）。
    }
    throw err; // 其它 IO 错误（权限等）向上抛出。
  }

  return JSON.parse(raw) as StructuredExport;
}

/**
 * 便捷方法：返回最新周的 Report_Identifier（即 {@link listAvailableWeeks} 的首项），
 * 无任何可用周次时返回 `null`。供仪表盘默认展示最新周使用。
 *
 * Req: 13.3
 */
export async function getLatestWeek(): Promise<string | null> {
  const weeks = await listAvailableWeeks();
  return weeks.length > 0 ? weeks[0] : null;
}
