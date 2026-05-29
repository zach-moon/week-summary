// frontend/components/Dashboard.tsx
//
// Dashboard——仪表盘布局装配组件，供 app/page.tsx（默认最新周）与
// app/week/[id]/page.tsx（指定周）复用（Req 13.2 / 13.3）。
//
// 依据 Claude Design mockup（summaey-2/views.jsx DashboardView）落地（任务 18.1）：
//   - 影院级深空背景（Cosmos）+ 鼠标视差（Parallax）
//   - sticky .dash-head：wordmark「Heliora」+ WeekSwitcher
//   - HeroBand：月球背景 + kicker(report_identifier · 日期范围) + headline + 三大数字
//   - DistributionBand(TimeDistribution) / CommitsBand(CommitList) /
//     CodexBand(CodexQuestions) / SuggestionBand(LlmSuggestions)
//   - footer
//   - 无数据周（total_commits==0 && total_sessions==0）展示 inline 空态
//
// 说明：StructuredExport 没有 'headline' 字段（mockup 的 data.js 额外字段，我们的
// 数据契约不含），故 hero 标题使用一个通用文案，不在类型上虚构 headline 字段。
//
// Server Component（数据由页面在服务端经 lib/data.ts 装配后传入）。Parallax / Cosmos /
// Reveal 等交互动效为客户端组件，作为子节点嵌入。

import Link from "next/link";

import type { StructuredExport } from "@/lib/types";

import { CodexQuestions } from "./CodexQuestions";
import { CommitList } from "./CommitList";
import { formatRange } from "./format";
import { LlmSuggestions } from "./LlmSuggestions";
import { Cosmos, Parallax, Reveal } from "./motion";
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

/** hero 通用标题——数据契约无 headline 字段，使用固定文案。 */
const HERO_HEADLINE = "这一周的开发足迹。";

export function Dashboard({ report, weeks, current }: DashboardProps) {
  const hasData =
    report.numbers.total_commits > 0 || report.numbers.total_sessions > 0;

  return (
    <Parallax className="dash">
      <Cosmos nebulae={["n1", "n2"]} />

      <header className="dash-head">
        <div className="dash-head-in">
          <span className="wordmark sm">
            <span className="wm-dot" />
            Heliora
          </span>
          <WeekSwitcher weeks={weeks} current={current} />
        </div>
      </header>

      {hasData ? (
        <>
          {/* ===== HeroBand：概览 ===== */}
          <section className="band hero-band" data-component="hero-band">
            <div className="hero-moon" aria-hidden="true">
              <span className="moon-glow" />
              <span className="moon-photo" />
            </div>
            <div className="wrap">
              <Reveal as="p" className="hero-kicker">
                {report.report_identifier} ·{" "}
                {formatRange(report.week_start, report.week_end)}
              </Reveal>
              <Reveal as="h1" className="hero-title" delay={70}>
                {HERO_HEADLINE}
              </Reveal>
              <NumbersPanel numbers={report.numbers} />
            </div>
          </section>

          <TimeDistribution distribution={report.distribution} />
          <CommitList repoCommits={report.repo_commits} />
          <CodexQuestions repoCodex={report.repo_codex} />
          <LlmSuggestions suggestions={report.llm_suggestions} />
        </>
      ) : (
        <section className="band band-base empty-inline" data-component="empty-inline">
          <div className="wrap">
            <Reveal className="empty-box">
              <span className="empty-mark" aria-hidden="true" />
              <h2 className="empty-title">该周暂无数据</h2>
              <p className="empty-sub">
                {report.report_identifier}（
                {formatRange(report.week_start, report.week_end)}
                ）还没有可汇总的提交或会话。
              </p>
              {weeks.length > 0 && weeks[0] !== current ? (
                <Link className="btn-ghost" href={`/week/${weeks[0]}`}>
                  回到最新周
                </Link>
              ) : (
                <Link className="btn-ghost" href="/">
                  回到最新周
                </Link>
              )}
            </Reveal>
          </div>
        </section>
      )}

      <footer className="dash-foot">
        <div className="wrap">
          <span>由本地 CLI 生成 · 不上传源码</span>
          <span className="dash-foot-id">{report.report_identifier}</span>
        </div>
      </footer>
    </Parallax>
  );
}

export default Dashboard;
