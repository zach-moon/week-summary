"use client";

// frontend/components/LoginView.tsx
//
// 登录页视觉外壳（LoginView）——依据 Claude Design mockup（summaey-2/views.jsx
// LoginView）落地（任务 18.1）：影院级深色，巨大写实半月压在左下角，cosmos 星云、
// 中心暗幕 scrim、鼠标跟随辉光、wordmark、巨标题「你这一周，都干了什么」带逐行上滑
// 入场动画、副标题、CTA 区与页脚。
//
// 仅负责视觉与入场动画（客户端）。真正的认证由调用方（登录页 server component）通过
// server action 触发——把「使用 GitHub 登录」表单作为 children 传入，渲染在 CTA 槽位，
// 从而保持 signIn("github") 的服务端认证接线不变。

import { useEffect, useRef, useState, type ReactNode } from "react";

interface LoginViewProps {
  /** CTA 槽位：调用方传入承载 signIn server action 的表单/按钮。 */
  children: ReactNode;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function LoginView({ children }: LoginViewProps) {
  const [shown, setShown] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // 入场：挂载后短暂延迟触发逐行上滑（reduce 时 CSS 已直接显示终态）。
  useEffect(() => {
    const t = setTimeout(() => setShown(true), 80);
    return () => clearTimeout(t);
  }, []);

  // 鼠标视差 + 跟随辉光：在根节点设置 --nx/--ny/--cx/--cy。
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    if (prefersReducedMotion()) return;
    let raf = 0;
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      const nx = ((e.clientX - r.left) / r.width - 0.5) * 2;
      const ny = ((e.clientY - r.top) / r.height - 0.5) * 2;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        el.style.setProperty("--nx", nx.toFixed(3));
        el.style.setProperty("--ny", ny.toFixed(3));
        el.style.setProperty("--cx", `${(e.clientX - r.left).toFixed(0)}px`);
        el.style.setProperty("--cy", `${(e.clientY - r.top).toFixed(0)}px`);
      });
    };
    const onLeave = () => {
      el.style.setProperty("--nx", "0");
      el.style.setProperty("--ny", "0");
    };
    el.addEventListener("mousemove", onMove);
    el.addEventListener("mouseleave", onLeave);
    return () => {
      el.removeEventListener("mousemove", onMove);
      el.removeEventListener("mouseleave", onLeave);
      cancelAnimationFrame(raf);
    };
  }, []);

  const inCls = (base: string) => `${base} ln ${shown ? "in" : ""}`;

  return (
    <div className="login" ref={rootRef}>
      <div className="cosmos" aria-hidden="true">
        <span className="neb n1" />
        <span className="neb n3" />
      </div>
      <div className="login-aura" aria-hidden="true">
        <div className="moon-layer">
          <span className="moon-glow lg" />
          <span className="moon-photo lg" />
        </div>
        <span className="login-scrim" />
        <span className="cursor-glow" />
      </div>

      <header className="login-top">
        <span className={"wordmark ln " + (shown ? "in" : "")}>
          <span className="wm-dot" />
          Heliora
        </span>
      </header>

      <main className="login-main">
        <h1 className="login-title">
          <span className="ln-mask">
            <span className={inCls("")} style={{ transitionDelay: "120ms" }}>
              你这一周，
            </span>
          </span>
          <span className="ln-mask">
            <span className={inCls("")} style={{ transitionDelay: "220ms" }}>
              都干了什么
            </span>
          </span>
        </h1>
        <p className={inCls("login-sub")} style={{ transitionDelay: "420ms" }}>
          把每周散落在各个仓库里的提交与思考，安静地汇成一处。
        </p>
        <div className={inCls("login-cta")} style={{ transitionDelay: "560ms" }}>
          {children}
          <p className="login-note">仅读取你授权仓库的提交与会话记录</p>
        </div>
      </main>

      <footer className={inCls("login-foot")} style={{ transitionDelay: "700ms" }}>
        本地生成 · 不上传源码
      </footer>
    </div>
  );
}

export default LoginView;
