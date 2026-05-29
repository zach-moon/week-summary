// frontend/components/EmptyState.tsx
//
// 无数据空态——请求的某一周不存在对应周报数据时展示「该周暂无数据」（Req 13.4）。
// 当提供 latestWeek 时，附带一个返回最新周的链接，方便用户回到有数据的视图。
//
// Server Component；基础 Tailwind 结构，最终样式在任务 18.1 落地。

import Link from "next/link";

interface EmptyStateProps {
  /** 最新可用周的 Report_Identifier；为空/未提供时不渲染返回链接。 */
  latestWeek?: string | null;
}

export function EmptyState({ latestWeek }: EmptyStateProps) {
  return (
    <section
      data-component="empty-state"
      className="space-y-3 py-12 text-center"
    >
      <p className="text-base text-gray-600">该周暂无数据</p>

      {latestWeek ? (
        <Link
          href={`/week/${latestWeek}`}
          data-latest-week={latestWeek}
          className="text-sm text-blue-600 hover:underline"
        >
          返回最新周（{latestWeek}）
        </Link>
      ) : null}
    </section>
  );
}

export default EmptyState;
