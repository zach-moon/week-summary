// frontend/__tests__/container.test.ts
//
// 容器与挂载集成 / 冒烟测试（task 20.2）—— SERVER tier 容器化与「挂载数据卷读取」契约。
//
// 覆盖：
//   - Req 15.1 前端 + Next.js 后端打包为 Docker 容器（提供 Dockerfile 与 docker-compose）：
//     对 next.config.js / Dockerfile / docker-compose.yml 做静态/配置冒烟校验
//     （standalone 输出、多阶段构建、非 root、CMD、只读 /data 挂载、env 注入）。
//   - Req 15.2 容器从挂载的数据卷读取 JSON Structured_Export：用真实的
//     loadReport / listAvailableWeeks（lib/data.ts）+ DATA_DIR 指向一个模拟 /data 的
//     临时目录，断言样例周报被正确读取——这正是容器内的代码路径（DATA_DIR env → 读 JSON）。
//   - Req 15.3 运行中新增 JSON 无需重建镜像即可被读取：在 DATA_DIR 指向的目录里
//     「运行时」写入一个新 <id>.json，再次调用 listAvailableWeeks/loadReport，
//     断言新周次立即出现且可读（函数每次调用都重新扫描目录）。
//
// 设计取舍（环境现实）：CI / sandbox 可能没有 Docker，且完整 `next build` + 镜像构建
// 很重。因此默认套件做「不依赖 Docker」的静态 + 真实代码路径校验；可选的 docker build
// 冒烟仅在显式设置 RUN_DOCKER_SMOKE=1 且 Docker 可用时运行，否则优雅跳过——保证
// 默认 `npm test` 在无 Docker 环境下全绿。
//
// ⚠️ lib/data.ts 在模块加载时即固定 `const DATA_DIR = process.env.DATA_DIR ?? "/data"`，
// 故凡需指向临时目录的用例，都先设置 process.env.DATA_DIR，再用 vi.resetModules() +
// 动态 import 重新加载模块（与 data-listweeks.props.test.ts 一致的 pattern）。

import { afterEach, describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import {
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { StructuredExport } from "@/lib/types";

// frontend 根目录：本测试文件位于 frontend/__tests__/，上跳一级即 frontend/。
const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** 读取 frontend 根目录下的文本文件（用于静态配置断言）。 */
function readRootFile(relPath: string): string {
  return readFileSync(path.join(FRONTEND_ROOT, relPath), "utf8");
}

/** 构造一份镜像 export.py `to_dict` 输出 schema 的样例 Structured_Export。 */
function makeSampleExport(id: string): StructuredExport {
  return {
    schema_version: 1,
    report_identifier: id,
    week_start: "2026-05-25",
    week_end: "2026-05-31",
    distribution: [
      {
        project_dir: "/home/dev/projects/week-summary",
        project_name: "week-summary",
        commit_count: 7,
        session_count: 3,
      },
    ],
    repo_commits: [
      {
        repo_id: "week-summary",
        repo_path: "/home/dev/projects/week-summary",
        commits: [{ date: "2026-05-26", subject: "feat: add container smoke test" }],
      },
    ],
    repo_codex: [
      {
        repo_id: "/home/dev/projects/week-summary",
        session_count: 3,
        themes: ["docker", "data volume"],
        key_questions: ["如何在不重建镜像的前提下读取新周报？"],
      },
    ],
    numbers: { total_commits: 7, total_sessions: 3, total_user_prompts: 12 },
    llm_suggestions: null,
  };
}

// =========================================================================== //
// Req 15.1 —— 容器化打包静态/配置冒烟校验（不依赖 Docker）。
// =========================================================================== //
describe("容器化打包配置 (Req 15.1)", () => {
  it("next.config.js 设置 output: 'standalone'（最小化运行镜像）", () => {
    const nextConfig = readRootFile("next.config.js");
    // 允许单/双引号；断言 standalone 输出已开启。
    expect(nextConfig).toMatch(/output:\s*["']standalone["']/);
  });

  it("Dockerfile 为多阶段构建（deps / builder / runner）", () => {
    const dockerfile = readRootFile("Dockerfile");
    expect(dockerfile).toMatch(/FROM\s+\S+\s+AS\s+deps/i);
    expect(dockerfile).toMatch(/FROM\s+\S+\s+AS\s+builder/i);
    expect(dockerfile).toMatch(/FROM\s+\S+\s+AS\s+runner/i);
  });

  it("Dockerfile 复制 standalone 产物、static 与 public 资源", () => {
    const dockerfile = readRootFile("Dockerfile");
    expect(dockerfile).toContain(".next/standalone");
    expect(dockerfile).toContain(".next/static");
    expect(dockerfile).toMatch(/COPY\s+--from=builder\s+\/app\/public\s+\.\/public/);
  });

  it("Dockerfile 以非 root 用户运行（创建用户并 USER 切换）", () => {
    const dockerfile = readRootFile("Dockerfile");
    expect(dockerfile).toMatch(/adduser\s+-S\s+nextjs/);
    expect(dockerfile).toMatch(/^\s*USER\s+nextjs\s*$/m);
  });

  it("Dockerfile 以 standalone 自带的 server.js 作为入口", () => {
    const dockerfile = readRootFile("Dockerfile");
    expect(dockerfile).toMatch(/CMD\s*\[\s*"node"\s*,\s*"server\.js"\s*\]/);
  });

  it("docker-compose.yml 以只读方式挂载数据卷到 /data (:ro)", () => {
    const compose = readRootFile("docker-compose.yml");
    // 卷映射 "<host>:/data:ro" —— 只读挂载（Req 15.2/15.3）。
    expect(compose).toMatch(/:\/data:ro/);
  });

  it("docker-compose.yml 通过环境变量注入运行所需参数（Req 15.4）", () => {
    const compose = readRootFile("docker-compose.yml");
    for (const key of [
      "GITHUB_CLIENT_ID",
      "GITHUB_CLIENT_SECRET",
      "AUTH_SECRET",
      "ALLOW_LIST",
      "AUTH_URL",
      "DATA_DIR",
    ]) {
      expect(compose).toContain(key);
    }
  });
});

// =========================================================================== //
// Req 15.2 / 15.3 —— 通过真实 lib/data.ts 验证「挂载数据卷读取」契约。
// 每个用例新建临时目录模拟 /data，设置 DATA_DIR 后 resetModules + 动态 import。
// =========================================================================== //
describe("挂载数据卷读取 (Req 15.2 / 15.3)", () => {
  const prevDataDir = process.env.DATA_DIR;
  let tmpDir: string | null = null;

  afterEach(async () => {
    if (tmpDir) {
      rmSync(tmpDir, { recursive: true, force: true });
      tmpDir = null;
    }
    if (prevDataDir === undefined) delete process.env.DATA_DIR;
    else process.env.DATA_DIR = prevDataDir;
    const { vi } = await import("vitest");
    vi.resetModules();
  });

  it("Req 15.2: 从挂载的数据卷目录读取样例 <id>.json", async () => {
    const { vi } = await import("vitest");
    tmpDir = mkdtempSync(path.join(os.tmpdir(), "data-vol-"));

    const idA = "2026-W21";
    const idB = "2026-W22";
    const sampleA = makeSampleExport(idA);
    const sampleB = makeSampleExport(idB);
    writeFileSync(path.join(tmpDir, `${idA}.json`), JSON.stringify(sampleA), "utf8");
    writeFileSync(path.join(tmpDir, `${idB}.json`), JSON.stringify(sampleB), "utf8");

    process.env.DATA_DIR = tmpDir;
    vi.resetModules();
    const { listAvailableWeeks, loadReport, getLatestWeek } = await import("@/lib/data");

    // 两个周次都被发现，降序排列（最新周在前）。
    await expect(listAvailableWeeks()).resolves.toEqual([idB, idA]);
    // 最新周便捷方法返回降序首项。
    await expect(getLatestWeek()).resolves.toBe(idB);
    // loadReport 读取并解析挂载卷中的 JSON，得到等价对象。
    await expect(loadReport(idA)).resolves.toEqual(sampleA);
    await expect(loadReport(idB)).resolves.toEqual(sampleB);
  });

  it("Req 15.3: 运行时新增的 JSON 无需重建即可被读取（每次调用重新扫描）", async () => {
    const { vi } = await import("vitest");
    tmpDir = mkdtempSync(path.join(os.tmpdir(), "data-vol-"));

    const existingId = "2026-W21";
    writeFileSync(
      path.join(tmpDir, `${existingId}.json`),
      JSON.stringify(makeSampleExport(existingId)),
      "utf8",
    );

    process.env.DATA_DIR = tmpDir;
    vi.resetModules();
    // 注意：仅在此处 import 一次（模拟「容器内长期运行的同一进程」），
    // 后续不再 resetModules——以证明无需重建/重载即可读到新文件。
    const { listAvailableWeeks, loadReport } = await import("@/lib/data");

    // 初始：只有一个周次。
    await expect(listAvailableWeeks()).resolves.toEqual([existingId]);

    // 运行时（容器内进程不变）写入一个新的周报 JSON（模拟 rsync/git push 同步进来）。
    const newId = "2026-W22";
    const newSample = makeSampleExport(newId);
    writeFileSync(path.join(tmpDir, `${newId}.json`), JSON.stringify(newSample), "utf8");

    // 再次扫描：新周次立即出现（无需重建镜像 / 重启进程），且可被 loadReport 读取。
    await expect(listAvailableWeeks()).resolves.toEqual([newId, existingId]);
    await expect(loadReport(newId)).resolves.toEqual(newSample);
  });
});

// =========================================================================== //
// 可选 Docker 构建冒烟（Req 15.1）——默认跳过；仅当 RUN_DOCKER_SMOKE=1 时尝试。
// 不阻塞默认 `npm test`：无 Docker / 未开启开关时优雅跳过，套件保持全绿。
// =========================================================================== //
function dockerAvailable(): boolean {
  try {
    execFileSync("docker", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

const runDockerSmoke = process.env.RUN_DOCKER_SMOKE === "1" && dockerAvailable();

describe.skipIf(!runDockerSmoke)("Docker 镜像构建冒烟 (Req 15.1, 可选)", () => {
  it("docker build 成功产出镜像", () => {
    // 重活：完整 next build + 多阶段镜像构建。仅在显式开启时运行。
    execFileSync(
      "docker",
      ["build", "-t", "weekly-dev-report-frontend:smoke", "."],
      { cwd: FRONTEND_ROOT, stdio: "inherit", timeout: 15 * 60 * 1000 },
    );
  });
});
