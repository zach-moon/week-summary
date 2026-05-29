// frontend/components/WeekSwitcher.tsx
//
// 周切换器（week switcher）——存在多周数据时提供按周切换入口（Req 13.3）。
// 由调用方传入 `weeks`（来自 lib/data.ts 的 listAvailableWeeks，已按降序排列）
// 与 `current`（当前展示的 Report_Identifier）。
//
// 纯展示组件：渲染指向 /week/[id] 的链接列表，高亮当前周。
// 简单链接列表无需客户端交互，保持为 Server Component（若日后改用下拉/select
// 需要交互，再标注 "use client"）。
//
// 基础 Tailwind 结构，最终样式在任务 18.1 落地。

import Link from "next/link";

interface WeekSwitcherProps {
  weeks: string[];
  current: string;
}

export function WeekSwitcher({ weeks, current }: WeekSwitcherProps) {
  if (weeks.length === 0) {
    return null;
  }

  return (
    <nav data-component="week-switcher" aria-label="周切换" className="space-y-2">
      <span className="text-sm font-medium text-gray-700">切换周次</span>
      <ul className="flex flex-wrap gap-2">
        {weeks.map((week) => {
          const isCurrent = week === current;
          return (
            <li key={week}>
              <Link
                href={`/week/${week}`}
                data-week={week}
                aria-current={isCurrent ? "page" : undefined}
                className={
                  isCurrent
                    ? "rounded-full bg-gray-900 px-3 py-1 text-sm font-medium text-white"
                    : "rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-700 hover:bg-gray-200"
                }
              >
                {week}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export default WeekSwitcher;
