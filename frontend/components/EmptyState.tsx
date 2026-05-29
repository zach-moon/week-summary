// frontend/components/EmptyState.tsx
//
// 无数据空态（centered-page / EmptyView）——请求的某一周不存在对应周报数据时展示
// 「该周暂无数据」（Req 13.4）。依据 Claude Design mockup 落地（任务 18.1）：影院级
// 居中页，cosmos 背景 + 底部升起的月球 + scrim + wordmark + .empty-mark + 大标题 +
// 「回到最新周」幽灵按钮（使用 latestWeek 链接到 /week/[id]）。
//
// 当 latestWeek 为空（连一周数据都没有）时省略返回链接。
//
// 使用 Reveal（客户端动效组件）；本组件本身无状态，作为 Server Component 渲染。

import Link from "next/link";

import { Cosmos, Reveal } from "./motion";

interface EmptyStateProps {
  /** 最新可用周的 Report_Identifier；为空/未提供时不渲染返回链接。 */
  latestWeek?: string | null;
}

export function EmptyState({ latestWeek }: EmptyStateProps) {
  return (
    <div className="centered-page" data-component="empty-state">
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
        <span className="empty-mark big" aria-hidden="true" />
        <h1 className="cp-title">该周暂无数据</h1>
        <p className="cp-sub">
          这一周还没有可汇总的提交或会话记录。
          <br />
          也许是休息了一周，也许 CLI 还没跑过。
        </p>
        {latestWeek ? (
          <Link
            className="btn-ghost"
            href={`/week/${latestWeek}`}
            data-latest-week={latestWeek}
          >
            回到最新一周
          </Link>
        ) : null}
      </Reveal>
    </div>
  );
}

export default EmptyState;
