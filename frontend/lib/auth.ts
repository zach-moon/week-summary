// frontend/lib/auth.ts
//
// Auth_Service —— GitHub OAuth + Allow_List 访问控制（Req 12）。
//
// 选型：采用 Auth.js (NextAuth v5) 的 GitHub provider，而非自研令牌交换。
// 授权码流程涉及 state/PKCE、令牌交换、会话 cookie 加密等安全细节，自研易出错；
// Auth.js 原生支持 App Router 的服务端会话与 middleware 保护。
//
// 必需的环境变量（凭证绝不入库，Req 15.4 / 12.5）：
//   - GITHUB_CLIENT_ID      GitHub OAuth App 的 client id
//   - GITHUB_CLIENT_SECRET  GitHub OAuth App 的 client secret
//   - ALLOW_LIST            逗号分隔的 GitHub 登录名白名单，例如 "alice,bob"
//   - AUTH_SECRET           Auth.js 会话/JWT 加密密钥（生产必填）
//   - AUTH_URL              站点 URL，生产必须为 https://...（OAuth 回调 + secure cookie）
//
// 说明：Auth.js 在 host 为 https 时默认使用 secure cookie（`__Secure-`/`__Host-`
// 前缀），且会话 cookie 始终为 httpOnly。因此生产部署设置 AUTH_URL=https://...
// 即可满足 Req 12.5（HTTPS 回调 + secure/httpOnly cookie）。

import NextAuth, { type NextAuthConfig } from "next-auth";
import GitHub from "next-auth/providers/github";

/**
 * 从 ALLOW_LIST 环境变量构造允许名单：逗号分隔、去空白、转小写、过滤空项。
 */
export function parseAllowList(raw: string | undefined | null): string[] {
  return (raw ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

/**
 * 纯函数：判断某个 GitHub 登录名是否在允许名单内（不区分大小写）。
 *
 * 返回 `true` 当且仅当 `login`（归一化为小写后）属于 `allowList`；
 * `login` 为 null/undefined/空白时返回 `false`（Property 19, Req 12.3）。
 *
 * 抽出为纯函数以便在隔离环境下做单元 / 属性测试（P19, task 16.2）。
 */
export function isAllowed(
  login: string | null | undefined,
  allowList: string[],
): boolean {
  if (!login) return false;
  const normalized = login.trim().toLowerCase();
  if (!normalized) return false;
  return allowList.includes(normalized);
}

const allowList = parseAllowList(process.env.ALLOW_LIST);

/**
 * Auth.js (NextAuth v5) 配置对象。
 *
 * 抽出为具名导出（而非内联进 `NextAuth(...)`），以便认证集成测试（task 16.3）
 * 能在隔离环境下直接调用真实的 `signIn` 回调，验证 Allow_List 校验 / OAuth
 * 拒绝场景（Req 12.2 / 12.4），无需启动 Next.js 运行时或发起真实 GitHub 网络请求。
 * 运行时行为与此前内联写法完全等价。
 */
export const authConfig = {
  providers: [
    GitHub({
      // 凭证仅来自环境变量（Req 15.4）。
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
    }),
  ],
  // 服务端会话采用 JWT 策略；cookie 在 https host 下默认 secure，且始终 httpOnly。
  session: { strategy: "jwt" },
  callbacks: {
    // Allow_List 校验：不在名单 -> 返回 false，不建立会话（Req 12.3）。
    async signIn({ profile }) {
      const login = profile?.login as string | undefined;
      return isAllowed(login, allowList);
    },
  },
  pages: {
    signIn: "/login", // 未认证 -> 重定向到登录入口（Req 12.1）
    error: "/unauthorized", // 拒绝 / OAuth 错误 -> 提示页（Req 12.3 / 12.4）
  },
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
