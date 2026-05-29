// frontend/components/TimeDistribution.tsx
//
// 时间分布（按项目目录聚合）——展示每个项目的 commit 数与会话数，并用一条
// 与「该项目活动量 / 最大活动量」成比例的简单条形可视化（Req 13.2）。
//
// 数据由 CLI 侧导出时已按 (commit_count, session_count) 降序排列（Req 5.3），
// 这里不再二次排序，直接按给定顺序渲染。
//
// 这是 Server Component（无交互）。样式仅用基础 Tailwind 维持可读结构，
// 最终 Apple 审美样式在任务 18.1 落地。

import type { ProjectDistribution } from "@/lib/types";

import { projectLabel } from "./format";

interface TimeDistributionProps {
  distribution: ProjectDistribution[];
}

/** 单个项目的「活动量」= commit 数 + 会话数，用于条形长度归一化。 */
function activity(entry: ProjectDistribution): number {
  return entry.commit_count + entry.session_count;
}

export function TimeDistribution({ distribution }: TimeDistributionProps) {
  // 以最大活动量为分母做比例归一化；全为 0 时避免除零。
  const maxActivity = distribution.reduce(
    (max, entry) => Math.max(max, activity(entry)),
    0,
  );

  return (
    <section data-component="time-distribution" className="space-y-4">
      <h2 className="text-lg font-semibold">时间分布</h2>

      {distribution.length === 0 ? (
        <p className="text-sm text-gray-500">本周暂无项目活动。</p>
      ) : (
        <ul className="space-y-3">
          {distribution.map((entry) => {
            const ratio =
              maxActivity > 0 ? activity(entry) / maxActivity : 0;
            const widthPct = Math.round(ratio * 100);
            return (
              <li
                key={entry.project_dir}
                data-project={entry.project_dir}
                className="space-y-1"
              >
                <div className="flex items-baseline justify-between gap-4 text-sm">
                  <span className="font-medium">{projectLabel(entry)}</span>
                  <span className="text-gray-500">
                    {entry.commit_count} commits · {entry.session_count} sessions
                  </span>
                </div>
                {/* 比例条：宽度反映相对活动量。仅作结构占位，样式后续可替换。 */}
                <div className="h-2 w-full rounded bg-gray-100">
                  <div
                    className="h-2 rounded bg-gray-400"
                    style={{ width: `${widthPct}%` }}
                    aria-hidden="true"
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default TimeDistribution;
