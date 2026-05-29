// frontend/app/unauthorized/page.tsx
//
// 「无访问权限」页——账户不在 Allow_List，或 OAuth 流程出错 / 拒绝授权时跳转到此
// （Req 12.3 / 12.4）。展示「该账户无访问权限」提示，并提供重新登录入口。
//
// 重新登录使用 server action：先 signOut 清理可能存在的会话残留，再回到 /login，
// 让用户可换用其它（在名单内的）GitHub 账户重试。
//
// Server Component；基础 Tailwind 结构，最终 Apple 审美样式在任务 18.1 落地。

import { signOut } from "@/lib/auth";

export default function UnauthorizedPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">无访问权限</h1>
        <p className="text-sm text-gray-500">
          该账户无访问权限。如使用了错误的账户，请重新登录后重试。
        </p>
      </div>

      <form
        action={async () => {
          "use server";
          await signOut({ redirectTo: "/login" });
        }}
      >
        <button
          type="submit"
          className="rounded-full bg-gray-900 px-5 py-2 text-sm font-medium text-white hover:bg-gray-700"
        >
          重新登录
        </button>
      </form>
    </main>
  );
}
