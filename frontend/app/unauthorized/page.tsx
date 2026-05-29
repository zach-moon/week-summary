// frontend/app/unauthorized/page.tsx
//
// 「无访问权限」页（UnauthorizedView）——账户不在 Allow_List，或 OAuth 流程出错 /
// 拒绝授权时跳转到此（Req 12.3 / 12.4）。展示「该账户暂无访问权限」提示，并提供重新
// 登录入口。
//
// 重新登录使用 server action：先 signOut 清理可能存在的会话残留，再回到 /login，
// 让用户可换用其它（在名单内的）GitHub 账户重试——认证接线保持不变。
//
// 视觉：依据 Claude Design mockup（summaey-2/views.jsx UnauthorizedView）落地
// （任务 18.1）的影院级居中页（cosmos + 底部月球 + scrim + lock-mark）。

import { Cosmos, Reveal } from "@/components";
import { signOut } from "@/lib/auth";

export default function UnauthorizedPage() {
  return (
    <div className="centered-page" data-component="unauthorized">
      <Cosmos nebulae={["n1"]} />
      <div className="cp-moon" aria-hidden="true">
        <span className="moon-glow" />
        <span className="moon-photo" />
      </div>
      <div className="cp-scrim" aria-hidden="true" />

      <header className="cp-top">
        <span className="wordmark">
          <span className="wm-dot" />
          Heliora
        </span>
      </header>

      <Reveal className="cp-body">
        <span className="lock-mark" aria-hidden="true" />
        <h1 className="cp-title">该账户暂无访问权限</h1>
        <p className="cp-sub">
          登录的 GitHub 账户不在允许名单内。
          <br />
          如果这是误会，请联系管理员把你加进来。
        </p>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/login" });
          }}
        >
          <button type="submit" className="btn-ghost">
            换个账户登录
          </button>
        </form>
      </Reveal>
    </div>
  );
}
