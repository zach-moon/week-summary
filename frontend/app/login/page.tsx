// frontend/app/login/page.tsx
//
// 登录页——GitHub 登录入口（Req 12.1）。
//
// 通过 server action 调用 signIn("github") 触发 GitHub OAuth 2.0 授权码流程。
// 若用户已认证则直接重定向到仪表盘 "/"，避免已登录用户停留在登录页。
//
// 视觉：依据 Claude Design mockup 落地（任务 18.1）的影院级 LoginView（深空 + 写实
// 半月）。LoginView 为客户端视觉外壳，承载 signIn 的 server action 表单作为其 CTA
// children 传入——认证接线（signIn("github")）保持不变，仅外观更新。

import { redirect } from "next/navigation";

import { GitHubMark, LoginView } from "@/components";
import { auth, signIn } from "@/lib/auth";

export default async function LoginPage() {
  // 已认证用户直接进入仪表盘。
  const session = await auth();
  if (session) {
    redirect("/");
  }

  return (
    <LoginView>
      <form
        className="login-cta-form"
        action={async () => {
          "use server";
          await signIn("github", { redirectTo: "/" });
        }}
      >
        <button type="submit" className="btn-gh">
          <GitHubMark size={20} />
          使用 GitHub 登录
        </button>
      </form>
    </LoginView>
  );
}
