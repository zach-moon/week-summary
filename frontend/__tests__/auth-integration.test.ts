// frontend/__tests__/auth-integration.test.ts
//
// 认证集成测试（task 16.3）—— Auth_Service（lib/auth.ts）+ 路由保护（middleware.ts）。
//
// 用 mock 的 OAuth profile 驱动真实的 `signIn` 回调与真实配置对象，覆盖：
//   - Req 12.1 未认证访问受保护路由 -> 重定向到登录入口（middleware matcher 保护
//     普通路由、放行 login/unauthorized/api/auth；pages.signIn === "/login"）。
//   - Req 12.2 名单内账户成功 -> signIn 回调返回 true（建立会话）。
//   - Req 12.4 OAuth 错误 / 拒绝授权 / profile 为 null 或缺 login -> signIn 返回 false
//     （保持未认证）；已认证但不在名单内同样返回 false（亦覆盖 Req 12.3）。
//
// 全程 hermetic：不发起任何真实 GitHub 网络请求，只调用纯逻辑回调与读取配置。
//
// 关键：lib/auth.ts 在模块求值时从 process.env.ALLOW_LIST 捕获 Allow_List（闭包于
// signIn 回调）。因此必须在「导入该模块之前」设置好环境变量——故本文件不静态导入
// lib/auth.ts，而是先设置 process.env，再在 beforeAll 中动态 import()。

import { beforeAll, describe, expect, it, vi } from "vitest";
import type { Profile } from "next-auth";

// `lib/auth.ts` 在模块加载时即调用 `NextAuth({...})`，会牵连 `next/server` 等仅在
// Next.js 运行时可用的依赖，在 node 测试环境下无法解析。这里仅打桩 next-auth 的
// 「框架装配」（NextAuth() 与 GitHub provider），不触碰被测对象本身——本测试断言的
// `authConfig.callbacks.signIn` 回调、`authConfig.pages` 与 middleware 的 `config`
// 都是我们自己的真实生产代码，不被该 mock 替换，从而保持集成测试的真实性与 hermetic。
vi.mock("next-auth", () => ({
  default: () => ({
    handlers: { GET: () => undefined, POST: () => undefined },
    auth: () => undefined,
    signIn: () => undefined,
    signOut: () => undefined,
  }),
}));
vi.mock("next-auth/providers/github", () => ({
  default: () => ({ id: "github" }),
}));

// ── 在动态导入 lib/auth.ts 之前固定环境（Req 15.4：凭证仅来自环境变量）──────────
// Allow_List 用大小写混合，顺带验证「归一化为小写」的名单匹配。
process.env.ALLOW_LIST = "Alice, bob";
process.env.GITHUB_CLIENT_ID = "test-client-id";
process.env.GITHUB_CLIENT_SECRET = "test-client-secret";
process.env.AUTH_SECRET = "test-auth-secret-not-a-real-secret";
process.env.AUTH_URL = "https://example.test";

// 在 beforeAll 中动态加载，确保上面的 env 在模块求值前已就绪。
type AuthModule = typeof import("@/lib/auth");
type MiddlewareModule = typeof import("@/middleware");

let authConfig: AuthModule["authConfig"];
let middlewareConfig: MiddlewareModule["config"];

/**
 * 以给定的 mock OAuth profile 调用真实的 signIn 回调。
 * signIn 回调只读取 `profile`，其余参数（user/account）以最小占位传入。
 */
async function runSignIn(profile: Profile | null | undefined): Promise<boolean | string> {
  const signInCallback = authConfig.callbacks?.signIn;
  if (!signInCallback) {
    throw new Error("signIn 回调未在 authConfig 中配置");
  }
  return signInCallback({
    // signIn 回调签名要求 user；本测试仅校验基于 profile 的 Allow_List 逻辑。
    user: { id: "mock-user" } as never,
    account: null,
    profile: profile ?? undefined,
  });
}

/** 把 Next.js middleware matcher 字符串编译为可在测试中匹配 pathname 的正则。 */
function matcherToRegExp(matcher: string): RegExp {
  return new RegExp(`^${matcher}$`);
}

beforeAll(async () => {
  const authModule = await import("@/lib/auth");
  const middlewareModule = await import("@/middleware");
  authConfig = authModule.authConfig;
  middlewareConfig = middlewareModule.config;
});

describe("Auth_Service 集成 — Req 12.2 名单内账户成功建立会话", () => {
  it("profile.login 在 Allow_List 内时 signIn 返回 true（建立会话）", async () => {
    await expect(runSignIn({ login: "bob" } as Profile)).resolves.toBe(true);
  });

  it("Allow_List 匹配不区分大小写（名单 'Alice' 命中登录名 'alice' / 'ALICE'）", async () => {
    await expect(runSignIn({ login: "alice" } as Profile)).resolves.toBe(true);
    await expect(runSignIn({ login: "ALICE" } as Profile)).resolves.toBe(true);
  });
});

describe("Auth_Service 集成 — Req 12.4 OAuth 错误/拒绝授权保持未认证", () => {
  it("profile 为 null（OAuth 错误/未返回 profile）时 signIn 返回 false", async () => {
    await expect(runSignIn(null)).resolves.toBe(false);
  });

  it("profile 为 undefined（拒绝授权 / denied consent）时 signIn 返回 false", async () => {
    await expect(runSignIn(undefined)).resolves.toBe(false);
  });

  it("profile 缺少 login 字段时 signIn 返回 false", async () => {
    await expect(runSignIn({ name: "No Login" } as Profile)).resolves.toBe(false);
  });

  it("空白 login 不被视为有效账户，signIn 返回 false", async () => {
    await expect(runSignIn({ login: "   " } as Profile)).resolves.toBe(false);
  });

  // 同时覆盖 Req 12.3：已通过 GitHub 认证但不在 Allow_List 内 -> 不建立会话。
  it("已认证但不在 Allow_List 内的账户 signIn 返回 false（不建立会话）", async () => {
    await expect(runSignIn({ login: "charlie" } as Profile)).resolves.toBe(false);
  });
});

describe("Auth_Service 集成 — Req 12.1 未认证访问受保护路由重定向到登录入口", () => {
  it("auth 配置将登录入口设为 /login（pages.signIn）", () => {
    expect(authConfig.pages?.signIn).toBe("/login");
    // 拒绝 / OAuth 错误的提示页（Req 12.3 / 12.4）。
    expect(authConfig.pages?.error).toBe("/unauthorized");
  });

  it("middleware matcher 保护普通路由（触发向 /login 的重定向）", () => {
    const matchers = middlewareConfig.matcher as string[];
    expect(Array.isArray(matchers)).toBe(true);
    const protect = matcherToRegExp(matchers[0]);

    // 受保护路由：未认证访问时由 Auth.js middleware 重定向到 pages.signIn。
    for (const pathname of ["/", "/week/2026-W22", "/dashboard", "/settings"]) {
      expect(protect.test(pathname)).toBe(true);
    }
  });

  it("middleware matcher 放行登录页 / 无权限页 / 认证端点（避免重定向自循环）", () => {
    const matchers = middlewareConfig.matcher as string[];
    const protect = matcherToRegExp(matchers[0]);

    // 公开/认证路由必须被排除在保护之外，否则未认证用户无法到达登录入口。
    for (const pathname of [
      "/login",
      "/unauthorized",
      "/api/auth/signin",
      "/api/auth/callback/github",
    ]) {
      expect(protect.test(pathname)).toBe(false);
    }
  });
});
