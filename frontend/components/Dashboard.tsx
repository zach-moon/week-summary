// frontend/components/Dashboard.tsx
//
// Dashboard——仪表盘布局装配组件，供 app/page.tsx（默认最新周）与
// app/week/[id]/page.tsx（指定周）复用，避免两处页面重复布局逻辑（Req 13.2 / 13.3）。
//
// 给定一份 StructuredExport（report）、可用周次列表（weeks）与当前周标识（current），
// 依次装配：
//   1. 头部：report_identifier（week_start ~ week_end）
//   2. 周切换器 WeekSwitcher（仅多周时出现，Req 13.3）
//   3. 时间分布 TimeDistribution（Req 13.2）
//   4. 数字 NumbersPanel（Req 13.2）
//   5. 本周做了什么 CommitList（Req 13.2）
//   6. 我提了什么关键问题 CodexQuestions（Req 13.2）
//   7. 自动建议 LlmSuggestions（仅 llm_suggestions 非 null 时出现，Req 6.6 / 6.7）
//
// Server Component（无交互、不读取数据，数据由页面在服务端经 lib/data.ts 装配后传入）。
// 基础 Tailwind 结构，最终 Apple 审美样式在任务 18.1 落地。

import type { StructuredExport } from "@/lib/types";

import { CodexQuestions } from "./CodexQuestions";
import { CommitList } from "./CommitList";
import { LlmSuggestions } from "./LlmSuggestions";
import { NumbersPanel } from "./NumbersPanel";
import { TimeDistribution } from "./TimeDistribution";
import { WeekSwitcher } from "./WeekSwitcher";

interface DashboardProps {
  /** 当前展示周的结构化数据。 */
  report: StructuredExport;
  /** 可用周次列表（来自 listAvailableWeeks，已按降序排列）。 */
  weeks: string[];
  /** 当前展示的 Report_Identifier。 */
  current: string;
}

export function Dashboard({ report, weeks, current }: DashboardProps) {
  return (
    <main
      data-component="dashboard"
      className="mx-auto max-w-3xl space-y-10 px-6 py-12"
    >
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          开发周报 {report.report_identifier}
        </h1>
        <p className="text-sm text-gray-500">
          {report.week_start} ~ {report.week_end}
        </p>
      </header>

      <WeekSwitcher weeks={weeks} current={current} />

      <TimeDistribution distribution={report.distribution} />

      <NumbersPanel numbers={report.numbers} />

      <CommitList repoCommits={report.repo_commits} />

      <CodexQuestions repoCodex={report.repo_codex} />

      <LlmSuggestions suggestions={report.llm_suggestions} />
    </main>
  );
}

export default Dashboard;
