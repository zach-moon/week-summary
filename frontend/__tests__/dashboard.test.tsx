// frontend/__tests__/dashboard.test.tsx
//
// 任务 17.3 — 组件 / 快照测试。
//
// 覆盖：
//   - Req 13.2：已认证用户打开仪表盘 → Dashboard 渲染四个内容区块
//     （时间分布 / commit / codex 关键问题 / 汇总数字）。
//   - Req 13.3：存在多周数据 → 周切换入口（WeekSwitcher）出现；
//     weeks 为空时不渲染任何内容。
//   - Req 13.4：请求的周无数据 → EmptyState 显示「该周暂无数据」；
//     零活动报告下 Dashboard 渲染 inline 空态（data-component="empty-inline"）。
//
// 渲染策略：vitest 环境为 "node"（无 jsdom）。组件包含 React Server Component 与
// "use client" 组件（WeekSwitcher 用 useState/useEffect/useRef、motion 用
// IntersectionObserver）。这些副作用只在 useEffect / 事件回调中触发，SSR 渲染期不执行，
// 因此用 react-dom/server 的 renderToStaticMarkup 渲染为静态 HTML 字符串，再对字符串
// 断言并配合 toMatchSnapshot()。计数动画（StatNumber/useCountUp）在 SSR 下停留在初始
// 值 0，故对「数字区块」断言其标签与标记，而非动画后的总数。
//
// next/link 在 node 下 SSR 用普通 <a> 替身（见 vi.mock）。
//
// 数据契约 fixture 内联构造，镜像 frontend/lib/types.ts 的 StructuredExport。
// 保持 hermetic：无网络、无文件系统。

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { Dashboard } from "@/components/Dashboard";
import { EmptyState } from "@/components/EmptyState";
import { WeekSwitcher } from "@/components/WeekSwitcher";
import type { StructuredExport } from "@/lib/types";

// next/link 在 node SSR 下用普通 <a> 替身：保留 href（含周 id）与子节点，
// 便于对切换入口的目标 id 做断言。在 factory 内动态 import react 以避免 mock 提升
// 与 ESM import 绑定的初始化顺序问题。
vi.mock("next/link", async () => {
  const React = await import("react");
  return {
    default: ({ href, children, ...rest }: { href: unknown; children?: unknown }) =>
      React.createElement(
        "a",
        { href: typeof href === "string" ? href : String(href), ...rest },
        children as never,
      ),
  };
});

// --------------------------------------------------------------------------- //
// Fixtures —— 内联构造合法 StructuredExport（镜像 lib/types.ts）。
// --------------------------------------------------------------------------- //

/** 含数据的报告：total_commits / total_sessions > 0，四区块均有内容。 */
function reportWithData(
  overrides: Partial<StructuredExport> = {},
): StructuredExport {
  return {
    schema_version: 1,
    report_identifier: "2026-W22",
    week_start: "2026-05-25",
    week_end: "2026-05-31",
    distribution: [
      {
        project_dir: "/Users/me/Projects/project-a",
        project_name: "project-a",
        commit_count: 12,
        session_count: 4,
      },
      {
        project_dir: "/Users/me/Projects/project-b",
        project_name: "project-b",
        commit_count: 3,
        session_count: 1,
      },
      {
        project_dir: "/Users/me/Projects/idle-project",
        project_name: "idle-project",
        commit_count: 0,
        session_count: 0,
      },
    ],
    repo_commits: [
      {
        repo_id: "project-a",
        repo_path: "/Users/me/Projects/project-a",
        commits: [
          { date: "2026-05-26", subject: "Add login route" },
          { date: "2026-05-27", subject: "Wire OAuth callback" },
        ],
      },
      {
        repo_id: "project-b",
        repo_path: "/Users/me/Projects/project-b",
        commits: [{ date: "2026-05-28", subject: "Fix pagination bug" }],
      },
    ],
    repo_codex: [
      {
        repo_id: "/Users/me/Projects/project-a",
        session_count: 4,
        themes: ["auth flow", "oauth callback"],
        key_questions: ["如何在 App Router 下保护路由？"],
      },
    ],
    numbers: {
      total_commits: 15,
      total_sessions: 5,
      total_user_prompts: 37,
    },
    llm_suggestions: null,
    ...overrides,
  };
}

/** 零活动报告：total_commits == 0 且 total_sessions == 0 → 触发 inline 空态。 */
function reportWithoutData(
  overrides: Partial<StructuredExport> = {},
): StructuredExport {
  return {
    schema_version: 1,
    report_identifier: "2026-W21",
    week_start: "2026-05-18",
    week_end: "2026-05-24",
    distribution: [],
    repo_commits: [],
    repo_codex: [],
    numbers: {
      total_commits: 0,
      total_sessions: 0,
      total_user_prompts: 0,
    },
    llm_suggestions: null,
    ...overrides,
  };
}

// --------------------------------------------------------------------------- //
// Req 13.2 —— 仪表盘渲染四个内容区块。
// --------------------------------------------------------------------------- //

describe("Dashboard 渲染四区块 (Req 13.2)", () => {
  const weeks = ["2026-W22", "2026-W21"];
  const report = reportWithData();
  const html = renderToStaticMarkup(
    <Dashboard report={report} weeks={weeks} current="2026-W22" />,
  );

  it("渲染时间分布、commit、codex 关键问题、汇总数字四个区块", () => {
    // 四个内容区块的 data-component 标记均出现。
    expect(html).toContain('data-component="time-distribution"');
    expect(html).toContain('data-component="commit-list"');
    expect(html).toContain('data-component="codex-questions"');
    expect(html).toContain('data-component="numbers-panel"');
  });

  it("各区块包含代表性内容", () => {
    // 时间分布：项目名。
    expect(html).toContain("project-a");
    // commit：提交标题与日期短格式（MM-DD）。
    expect(html).toContain("Add login route");
    expect(html).toContain("Fix pagination bug");
    expect(html).toContain("05-26");
    // codex 关键问题：主题与问题文本。
    expect(html).toContain("auth flow");
    expect(html).toContain("如何在 App Router 下保护路由？");
    // 数字区块：三项标签（动画后的总数在 SSR 下为 0，故断言标签而非数值）。
    expect(html).toContain("提交 commit");
    expect(html).toContain("Codex 会话");
    expect(html).toContain("提问总数");
    // hero kicker：report_identifier 与起止日期范围。
    expect(html).toContain("2026-W22");
    expect(html).toContain("05-25 ~ 05-31");
  });

  it("不渲染 inline 空态（有数据时）", () => {
    expect(html).not.toContain('data-component="empty-inline"');
  });

  it("快照", () => {
    expect(html).toMatchSnapshot();
  });
});

// --------------------------------------------------------------------------- //
// Req 13.3 —— 多周下周切换入口出现 / weeks 为空时不渲染。
// --------------------------------------------------------------------------- //

describe("周切换入口 (Req 13.3)", () => {
  it("多周数据下 Dashboard 含 week-switcher 入口", () => {
    const html = renderToStaticMarkup(
      <Dashboard
        report={reportWithData()}
        weeks={["2026-W22", "2026-W21"]}
        current="2026-W22"
      />,
    );
    expect(html).toContain('data-component="week-switcher"');
  });

  it("WeekSwitcher 渲染当前周 id 与相邻周的切换目标", () => {
    const weeks = ["2026-W23", "2026-W22", "2026-W21"];
    const html = renderToStaticMarkup(
      <WeekSwitcher weeks={weeks} current="2026-W22" />,
    );
    expect(html).toContain('data-component="week-switcher"');
    // 当前周 id 出现在中心标签。
    expect(html).toContain("2026-W22");
    // 「下一周」（更新）与「上一周」（更早）导航目标 href 含相邻周 id。
    expect(html).toContain('href="/week/2026-W23"');
    expect(html).toContain('href="/week/2026-W21"');
  });

  it("weeks 为空时 WeekSwitcher 不渲染任何内容", () => {
    const html = renderToStaticMarkup(<WeekSwitcher weeks={[]} current="" />);
    expect(html).toBe("");
  });

  it("快照（多周切换器）", () => {
    const html = renderToStaticMarkup(
      <WeekSwitcher weeks={["2026-W23", "2026-W22", "2026-W21"]} current="2026-W22" />,
    );
    expect(html).toMatchSnapshot();
  });
});

// --------------------------------------------------------------------------- //
// Req 13.4 —— 无数据提示。
// --------------------------------------------------------------------------- //

describe("无数据提示 (Req 13.4)", () => {
  it("EmptyState 渲染「该周暂无数据」", () => {
    const html = renderToStaticMarkup(<EmptyState latestWeek="2026-W22" />);
    expect(html).toContain('data-component="empty-state"');
    expect(html).toContain("该周暂无数据");
    // 提供「回到最新一周」链接，目标为 latestWeek。
    expect(html).toContain('href="/week/2026-W22"');
  });

  it("EmptyState 在无任何周数据时省略返回链接", () => {
    const html = renderToStaticMarkup(<EmptyState latestWeek={null} />);
    expect(html).toContain("该周暂无数据");
    expect(html).not.toContain("回到最新一周");
  });

  it("零活动报告下 Dashboard 渲染 inline 空态并含「该周暂无数据」", () => {
    const html = renderToStaticMarkup(
      <Dashboard
        report={reportWithoutData()}
        weeks={["2026-W22", "2026-W21"]}
        current="2026-W21"
      />,
    );
    expect(html).toContain('data-component="empty-inline"');
    expect(html).toContain("该周暂无数据");
    // inline 空态不渲染四区块内容。
    expect(html).not.toContain('data-component="time-distribution"');
    expect(html).not.toContain('data-component="numbers-panel"');
  });

  it("快照（EmptyState）", () => {
    const html = renderToStaticMarkup(<EmptyState latestWeek="2026-W22" />);
    expect(html).toMatchSnapshot();
  });
});
