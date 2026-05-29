"use client";

// frontend/components/motion.tsx
//
// 共享客户端动效与图标助手——从 Claude Design mockup（summaey-2/ui.jsx）移植
// （任务 18.1 / Req 13.2）。包含：
//   - useInView：进入视区检测（IntersectionObserver）
//   - useCountUp：数字从 0 缓动到目标值
//   - Reveal：滚动渐显包裹
//   - ProportionBar：占比条（进入视区后展开）
//   - StatNumber：hero 大数字 + 计数动画
//   - GitHubMark / Chevron / Caret：图标
//
// 全部尊重 prefers-reduced-motion：减少动效时直接显示终态、跳过过渡。

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from "react";

/** 是否处于「减少动效」偏好。SSR 期默认 false（终态由 CSS 媒体查询兜底）。 */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** 进入视区检测：元素首次进入视口后置 inView=true 并停止观察。 */
export function useInView<T extends HTMLElement = HTMLDivElement>(opts?: {
  threshold?: number;
  rootMargin?: string;
}): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // 无 IntersectionObserver（或 reduce）时直接显示终态。
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setInView(true);
            io.unobserve(el);
          }
        });
      },
      {
        threshold: opts?.threshold ?? 0.14,
        rootMargin: opts?.rootMargin ?? "0px 0px -6% 0px",
      },
    );
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return [ref, inView];
}

/** 数字滚动计数：进入视区后从 0 缓动到 target。reduce 时直接落到 target。 */
export function useCountUp(target: number, inView: boolean, dur = 1200): number {
  const [val, setVal] = useState(0);

  useEffect(() => {
    if (!inView) return;
    if (prefersReducedMotion()) {
      setVal(target);
      return;
    }
    let raf = 0;
    let start: number | undefined;
    const ease = (t: number) => 1 - Math.pow(1 - t, 4);
    const step = (ts: number) => {
      if (start === undefined) start = ts;
      const p = Math.min(1, (ts - start) / dur);
      setVal(Math.round(ease(p) * target));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [inView, target, dur]);

  return val;
}

interface RevealProps {
  children: ReactNode;
  delay?: number;
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
}

/** 通用滚动渐显包裹。进入视区后添加 .is-in 触发 CSS 过渡。 */
export function Reveal({
  children,
  delay = 0,
  as: Tag = "div",
  className = "",
  style = {},
}: RevealProps) {
  const [ref, inView] = useInView();
  return (
    <Tag
      ref={ref}
      className={"reveal " + (inView ? "is-in " : "") + className}
      style={{ transitionDelay: `${delay}ms`, ...style }}
    >
      {children}
    </Tag>
  );
}

/** 占比条：进入视区后从 0 展开到 pct%。 */
export function ProportionBar({
  pct,
  shown,
  delay = 0,
}: {
  pct: number;
  shown: boolean;
  delay?: number;
}) {
  return (
    <div className="pbar">
      <div
        className="pbar-fill"
        style={{
          width: (shown ? Math.max(pct, 1.5) : 0) + "%",
          transitionDelay: `${delay}ms`,
        }}
        aria-hidden="true"
      />
    </div>
  );
}

/** hero 大数字 + 进入视区计数动画。 */
export function StatNumber({
  value,
  label,
  delay = 0,
}: {
  value: number;
  label: string;
  delay?: number;
}) {
  const [ref, inView] = useInView({ threshold: 0.35 });
  const v = useCountUp(value, inView, 1300);
  return (
    <div
      ref={ref}
      className={"stat reveal " + (inView ? "is-in " : "")}
      style={{ transitionDelay: `${delay}ms` }}
    >
      <span className="stat-v tnum">{v}</span>
      <span className="stat-l">{label}</span>
    </div>
  );
}

/** GitHub 标记图标（登录按钮用）。 */
export function GitHubMark({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

/** 左右箭头（周切换导航）。 */
export function Chevron({
  dir = "left",
  size = 18,
}: {
  dir?: "left" | "right";
  size?: number;
}) {
  const d = dir === "left" ? "M11 4 6 9l5 5" : "M7 4l5 5-5 5";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden="true"
    >
      <path
        d={d}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** 下拉指示三角。 */
export function Caret({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 14 14"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3.5 5.5 7 9l3.5-3.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}


/** 共享宇宙背景层：缓慢漂移的星云（纯装饰，pointer-events:none）。 */
export function Cosmos({ nebulae = ["n1", "n2"] }: { nebulae?: string[] }) {
  return (
    <div className="cosmos" aria-hidden="true">
      {nebulae.map((n) => (
        <span key={n} className={`neb ${n}`} />
      ))}
    </div>
  );
}

interface ParallaxProps {
  children: ReactNode;
  className?: string;
}

/**
 * 鼠标视差容器：在自身上设置 --nx/--ny(-1..1) 与 --cx/--cy(px)，
 * 子层（月球、星云）用 translate 响应。reduce 时不绑定监听。
 */
export function Parallax({ children, className = "" }: ParallaxProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
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

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
