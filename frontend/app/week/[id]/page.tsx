// frontend/app/week/[id]/page.tsx
//
// 指定周视图（受保护）——展示某一指定 Report_Identifier 的周报（Req 13.2 / 13.3 / 13.4）。
//
// Server Component：在服务端经 lib/data.ts 读取数据并装配组件。
//   - loadReport(id) 为 null（该周无对应 JSON）→ 渲染 EmptyState「该周暂无数据」，
//     并附返回最新周链接（Req 13.4）。
//   - 否则用 Dashboard 装配与首页一致的仪表盘布局，current = id。
//
// Next.js 15 注意：动态路由的 `params` 为异步（Promise），必须 await 后再取值，
// 否则类型检查与构建会失败。
//
// 路由保护由 middleware.ts 统一处理；lib/data.ts 为 server-only，仅在服务端导入。

import { Dashboard, EmptyState } from "@/components";
import { getLatestWeek, listAvailableWeeks, loadReport } from "@/lib/data";

// 每次请求都重新读取数据目录，新同步进来的周报无需重建即可展示（Req 15.3）。
export const dynamic = "force-dynamic";

interface WeekPageProps {
  // Next.js 15：params 是 Promise，需 await。
  params: Promise<{ id: string }>;
}

export default async function WeekPage({ params }: WeekPageProps) {
  const { id } = await params;

  const report = await loadReport(id);

  // 请求的周无对应数据 → 「该周暂无数据」，并提供返回最新周入口（Req 13.4）。
  if (report === null) {
    const latestWeek = await getLatestWeek();
    return <EmptyState latestWeek={latestWeek} />;
  }

  const weeks = await listAvailableWeeks();

  return <Dashboard report={report} weeks={weeks} current={id} />;
}
