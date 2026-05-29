// frontend/components/NumbersPanel.tsx
//
// 数字（HeroBand stats）——展示三项汇总大数字：提交 commit / Codex 会话 / 提问总数
// （Req 13.2）。依据 Claude Design mockup 落地（任务 18.1）：.stats 三栏，每项一个
// 巨大的 .stat-v 数字 + .stat-l 标签，数字带进入视区计数动画（StatNumber，客户端）。
//
// 消费 StructuredExport["numbers"]。本组件渲染 .stats 网格，由 Dashboard 的 HeroBand
// 包裹（kicker + headline + 月球背景）。
//
// 作为 Server Component 渲染（StatNumber 自身为客户端组件，负责计数动画）。

import type { StructuredExport } from "@/lib/types";

import { StatNumber } from "./motion";

interface NumbersPanelProps {
  numbers: StructuredExport["numbers"];
}

export function NumbersPanel({ numbers }: NumbersPanelProps) {
  return (
    <div className="stats" data-component="numbers-panel">
      <StatNumber value={numbers.total_commits} label="提交 commit" delay={120} />
      <StatNumber value={numbers.total_sessions} label="Codex 会话" delay={220} />
      <StatNumber
        value={numbers.total_user_prompts}
        label="提问总数"
        delay={320}
      />
    </div>
  );
}

export default NumbersPanel;
