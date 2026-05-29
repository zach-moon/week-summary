// frontend/__tests__/data-listweeks.props.test.ts
//
// Feature: weekly-dev-report, Property (task 15.4): listAvailableWeeks 文件名集合一致
//
// 对任意一组 `<id>.json` 文件名集合（混入噪声：非 json 文件、子目录、含点/空格等
// 不安全 id 的文件），`listAvailableWeeks()` 应恰好返回对应的 Report_Identifier 集合
// （仅 `*.json`，去除扩展名，且仅保留匹配安全模式 /^[A-Za-z0-9_-]+$/ 的 id），并按降序排列。
//
// Validates: Requirements 13.3, 15.3
//
// 实现要点：`lib/data.ts` 在模块加载时即固定 `DATA_DIR = process.env.DATA_DIR ?? "/data"`，
// 因此每轮迭代都新建临时目录、设置 `process.env.DATA_DIR`，再用 `vi.resetModules()` +
// 动态 import 重新加载模块，使其读取最新的 DATA_DIR。

import { describe, it, expect, vi, afterEach } from "vitest";
import fc from "fast-check";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  rmSync,
  existsSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";

// 安全 id 字符集，与 lib/data.ts 中的 SAFE_ID = /^[A-Za-z0-9_-]+$/ 一致。
const SAFE_CHARS =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-".split("");

// 生成一个非空、仅含安全字符的 id。
const safeIdArb = fc
  .array(fc.constantFrom(...SAFE_CHARS), { minLength: 1, maxLength: 12 })
  .map((cs) => cs.join(""));

// 一组互不相同的安全 id；用 toLowerCase 作为去重键，避免在大小写不敏感的文件系统
// （如 macOS 默认 APFS）上 `Abc.json` 与 `abc.json` 互相覆盖造成集合不一致。
const safeIdsArb = fc.uniqueArray(safeIdArb, {
  selector: (s) => s.toLowerCase(),
  minLength: 0,
  maxLength: 12,
});

// 噪声文件名片段：这些条目落盘后都不应进入结果集合。
const noiseArb = fc.record({
  // 非 json 文件（扩展名不是 .json）→ 被排除。
  txt: fc.array(safeIdArb, { maxLength: 5 }),
  // 含点的 json 文件 `<base>.seg.json` → 去扩展名后为 `<base>.seg`，含 `.`，不匹配安全模式 → 被排除。
  dotted: fc.array(safeIdArb, { maxLength: 5 }),
  // 含空格的 json 文件 `<base> x.json` → 去扩展名后含空格，不匹配安全模式 → 被排除。
  spaced: fc.array(safeIdArb, { maxLength: 5 }),
  // 无扩展名文件 → 被排除。
  plain: fc.array(safeIdArb, { maxLength: 5 }),
  // 名为 `<base>.json` 的子目录 → 不是文件（isFile() 为 false）→ 被排除。
  dirs: fc.array(safeIdArb, { maxLength: 5 }),
});

// 与 lib/data.ts 中一致的降序比较器（字典序降序，最新周在前）。
const descending = (a: string, b: string) => (a < b ? 1 : a > b ? -1 : 0);

describe("listAvailableWeeks — 文件名集合一致 (property, task 15.4)", () => {
  const prevDataDir = process.env.DATA_DIR;

  afterEach(() => {
    if (prevDataDir === undefined) delete process.env.DATA_DIR;
    else process.env.DATA_DIR = prevDataDir;
    vi.resetModules();
  });

  it("对任意 *.json 文件名集合恰好返回去扩展名后的安全 Report_Identifier 集合（降序）", async () => {
    await fc.assert(
      fc.asyncProperty(safeIdsArb, noiseArb, async (validIds, noise) => {
        const dir = mkdtempSync(path.join(os.tmpdir(), "lsw-"));
        try {
          // 1) 写入有效的 `<safe-id>.json` 文件（小写扩展名）。
          for (const id of validIds) {
            writeFileSync(path.join(dir, `${id}.json`), "{}", "utf8");
          }

          // 2) 写入各类噪声；用 existsSync 防御性跳过与已有有效文件的潜在路径冲突。
          for (const b of noise.txt) {
            const p = path.join(dir, `${b}.txt`);
            if (!existsSync(p)) writeFileSync(p, "x", "utf8");
          }
          for (const b of noise.dotted) {
            const p = path.join(dir, `${b}.seg.json`);
            if (!existsSync(p)) writeFileSync(p, "{}", "utf8");
          }
          for (const b of noise.spaced) {
            const p = path.join(dir, `${b} x.json`);
            if (!existsSync(p)) writeFileSync(p, "{}", "utf8");
          }
          for (const b of noise.plain) {
            const p = path.join(dir, `${b}`);
            if (!existsSync(p)) writeFileSync(p, "x", "utf8");
          }
          for (const b of noise.dirs) {
            const p = path.join(dir, `${b}.json`);
            if (!existsSync(p)) mkdirSync(p);
          }

          // 3) 指向临时目录并重新加载模块（DATA_DIR 在模块加载时被固定）。
          process.env.DATA_DIR = dir;
          vi.resetModules();
          const { listAvailableWeeks } = await import("@/lib/data");

          const result = await listAvailableWeeks();
          const expected = [...validIds].sort(descending);

          // 严格相等：既校验「恰好是安全 id 集合」（无遗漏/无多余），也校验「降序排列」。
          expect(result).toEqual(expected);
        } finally {
          rmSync(dir, { recursive: true, force: true });
        }
      }),
      { numRuns: 100 },
    );
  });
});
