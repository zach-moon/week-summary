// Feature: weekly-dev-report, Property 19: Allow_List 校验
//
// For any GitHub 登录名 `login` 与 Allow_List 名单，`Auth_Service` 的 `signIn`
// 回调返回 `true`（建立会话）当且仅当 `login`（不区分大小写）属于该名单；否则
// 拒绝且不建立会话。
//
// 这里测试 signIn 回调的可测核心——纯函数 `isAllowed(login, allowList)`。
// Allow_List 由 `parseAllowList` 归一化为「小写、去首尾空白、非空」的数组，
// 因此测试中生成的名单也保持该不变量。
//
// Validates: Requirements 12.3

import { describe, it, expect, vi } from "vitest";
import fc from "fast-check";

// `lib/auth.ts` 在模块加载时即调用 `NextAuth({...})`，会牵连 `next/server` 等
// 仅在 Next.js 运行时可用的依赖，在 node 测试环境下无法解析。被测对象
// `isAllowed`/`parseAllowList` 是与该框架初始化无关的纯函数，因此这里仅打桩
// next-auth 的框架装配（不触碰被测函数本身），使纯函数得以在隔离环境下加载与测试。
vi.mock("next-auth", () => ({
  default: () => ({
    handlers: {},
    auth: () => undefined,
    signIn: () => undefined,
    signOut: () => undefined,
  }),
}));
vi.mock("next-auth/providers/github", () => ({
  default: () => ({}),
}));

import { isAllowed, parseAllowList } from "@/lib/auth";

// 与 isAllowed 内部一致的归一化：去首尾空白后转小写。
function normalize(login: string | null | undefined): string {
  return (login ?? "").trim().toLowerCase();
}

// 独立的 oracle（不调用 isAllowed）：归一化后非空且属于（已归一化的）名单。
function expectedAllowed(
  login: string | null | undefined,
  allowList: string[],
): boolean {
  const n = normalize(login);
  return n.length > 0 && allowList.includes(n);
}

// GitHub 登录名字符集（小写字母 / 数字 / 连字符）——避免 Unicode 大小写折叠的
// 边界（如 'ß'/'İ'），使大小写变换可干净往返。
const LOGIN_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-".split("");
const loginChar = fc.constantFrom(...LOGIN_CHARS);

// 已归一化的登录名：非空、小写、无首尾空白。
const normalizedLogin = fc
  .array(loginChar, { minLength: 1, maxLength: 15 })
  .map((chars) => chars.join(""));

// 已归一化、去重的 Allow_List（模拟 parseAllowList 的输出）。
const allowListArb = fc.uniqueArray(normalizedLogin, { maxLength: 8 });

// 首尾空白片段（trim 会移除）。
const whitespace = fc
  .array(fc.constantFrom(" ", "\t"), { maxLength: 3 })
  .map((a) => a.join(""));

// 对 base 做随机大小写 + 首尾空白变换；其归一化值仍等于 base。
function variantOf(base: string): fc.Arbitrary<string> {
  return fc
    .tuple(
      fc.array(fc.boolean(), { minLength: base.length, maxLength: base.length }),
      whitespace,
      whitespace,
    )
    .map(([flags, lead, trail]) => {
      const body = base
        .split("")
        .map((c, i) => (flags[i] ? c.toUpperCase() : c))
        .join("");
      return lead + body + trail;
    });
}

const randomLogin = fc.string({ maxLength: 20 });
const emptyish = fc.constantFrom("", " ", "  ", "\t", " \t ");
const nullish = fc.constantFrom(null, undefined);

// 场景：先生成名单，再从多种来源生成 login——
//  - 名单成员的大小写/空白变体（应被接受）
//  - 任意随机串（多半不在名单）
//  - 空 / 纯空白 / null / undefined（应被拒绝）
const scenario = allowListArb.chain((allowList) => {
  const branches: fc.Arbitrary<string | null | undefined>[] = [
    randomLogin,
    emptyish,
    nullish,
  ];
  if (allowList.length > 0) {
    branches.unshift(
      fc.constantFrom(...allowList).chain((base) => variantOf(base)),
    );
  }
  return fc
    .oneof(...branches)
    .map((login) => [login, allowList] as [string | null | undefined, string[]]);
});

describe("Property 19: Allow_List 校验 (isAllowed)", () => {
  it("isAllowed 返回 true 当且仅当归一化后的非空 login 属于名单", () => {
    fc.assert(
      fc.property(scenario, ([login, allowList]) => {
        expect(isAllowed(login, allowList)).toBe(
          expectedAllowed(login, allowList),
        );
      }),
      { numRuns: 200 },
    );
  });

  // 例子 / 边界，配合属性测试覆盖文档中明确点名的场景。
  it("大小写不敏感：'Alice' 命中 'alice'", () => {
    expect(isAllowed("Alice", ["alice"])).toBe(true);
    expect(isAllowed("ALICE", ["alice"])).toBe(true);
    expect(isAllowed("  Bob  ", parseAllowList("alice, BOB"))).toBe(true);
  });

  it("不在名单 / 空 / 空白 / null / undefined => false", () => {
    expect(isAllowed("carol", ["alice", "bob"])).toBe(false);
    expect(isAllowed("", ["alice"])).toBe(false);
    expect(isAllowed("   ", ["alice"])).toBe(false);
    expect(isAllowed(null, ["alice"])).toBe(false);
    expect(isAllowed(undefined, ["alice"])).toBe(false);
    expect(isAllowed("alice", [])).toBe(false);
  });
});
