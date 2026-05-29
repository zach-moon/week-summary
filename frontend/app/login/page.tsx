// frontend/app/login/page.tsx
//
// 登录页——GitHub 登录入口（Req 12.1）。
//
// 通过 server action 调用 signIn("github") 触发 GitHub OAuth 2.0 授权码流程。
// 若用户已认证则直接重定向到仪表盘 "/"，避免已登录用户停留在登录页。
//
// Server Component；基础 Tailwind 结构，最终 Apple 审美样式在任务 18.1 落地。

import { redirect } from "next/navigation";

import { auth, signIn } from "@/lib/auth";

export default async function LoginPage() {
  // 已认证用户直接进入仪表盘。
  const session = await auth();
  if (session) {
    redirect("/");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">开发周报</h1>
        <p className="text-sm text-gray-500">
          请使用 GitHub 账户登录以查看开发周报。
        </p>
      </div>

      <form
        action={async () => {
          "use server";
          await signIn("github", { redirectTo: "/" });
        }}
      >
        <button
          type="submit"
          className="rounded-full bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700"
        >
          使用 GitHub 登录
        </button>
      </form>
    </main>
  );
}
