// frontend/components/NumbersPanel.tsx
//
// 数字——展示三项汇总数字：commit 总数、Codex 会话总数、提问（User_Prompt）总数
// （Req 13.2）。消费 StructuredExport["numbers"]。
//
// Server Component；基础 Tailwind 结构，最终样式在任务 18.1 落地。

import type { StructuredExport } from "@/lib/types";

interface NumbersPanelProps {
  numbers: StructuredExport["numbers"];
}

/** 三项统计的展示配置：键、中文标签。 */
const STATS: { key: keyof StructuredExport["numbers"]; label: string }[] = [
  { key: "total_commits", label: "commit 总数" },
  { key: "total_sessions", label: "Codex 会话总数" },
  { key: "total_user_prompts", label: "提问总数" },
];

export function NumbersPanel({ numbers }: NumbersPanelProps) {
  return (
    <section data-component="numbers-panel" className="space-y-4">
      <h2 className="text-lg font-semibold">数字</h2>

      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {STATS.map((stat) => (
          <div
            key={stat.key}
            data-stat={stat.key}
            className="space-y-1 rounded-lg bg-gray-50 p-4"
          >
            <dt className="text-sm text-gray-500">{stat.label}</dt>
            <dd className="text-3xl font-semibold tabular-nums">
              {numbers[stat.key]}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default NumbersPanel;
