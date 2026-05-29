"use client";

// frontend/components/TimeDistribution.tsx
//
// 精力分布（DistributionBand）——展示每个项目的 commit 数与会话数，并用占比条可视化
// （Req 13.2）。依据 Claude Design mockup 落地（任务 18.1）：eyebrow「精力分布」+
// band-title + .dist 行（.pbar 占比条）。
//
// 占比条宽度 = commit_count / max(commit_count)；commit_count==0 && session_count==0
// 的行标记为 .idle（弱化样式），与 mockup 一致。
//
// 数据由 CLI 侧导出时已按 (commit_count, session_count) 降序排列（Req 5.3），按序渲染。
//
// 客户端组件：使用 useInView 触发占比条进入视区后的展开动画。

import type { ProjectDistribution } from "@/lib/types";

import { projectLabel } from "./format";
import { ProportionBar, Reveal, useInView } from "./motion";

interface TimeDistributionProps {
  distribution: ProjectDistribution[];
}

export function TimeDistribution({ distribution }: TimeDistributionProps) {
  const [ref, inView] = useInView<HTMLElement>({ threshold: 0.2 });

  // 占比条以「最大 commit 数」为分母（与 mockup 一致），避免除零。
  const max = Math.max(
    1,
    ...distribution.map((d) => d.commit_count),
  );

  return (
    <section className="band band-alt" ref={ref} data-component="time-distribution">
      <div className="wrap">
        <Reveal as="p" className="eyebrow">
          精力分布
        </Reveal>
        <Reveal as="h2" className="band-title">
          这一周，时间花在了哪里
        </Reveal>

        {distribution.length === 0 ? (
          <p className="empty-sub">本周暂无项目活动。</p>
        ) : (
          <div className="dist">
            {distribution.map((d, i) => {
              const pct = (d.commit_count / max) * 100;
              const idle = d.commit_count === 0 && d.session_count === 0;
              return (
                <div
                  className={"dist-row " + (idle ? "idle" : "")}
                  key={d.project_dir}
                  data-project={d.project_dir}
                >
                  <span className="dist-name">{projectLabel(d)}</span>
                  <ProportionBar pct={pct} shown={inView} delay={120 + i * 70} />
                  <span className="dist-meta">
                    <b>{d.commit_count}</b> commit
                    <span className="dist-sep">·</span>
                    <b>{d.session_count}</b> 会话
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

export default TimeDistribution;
