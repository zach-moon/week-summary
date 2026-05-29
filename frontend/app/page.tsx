// frontend/app/page.tsx
//
// 仪表盘首页（受保护）——默认展示最新一周的周报（Req 13.2 / 13.3）。
//
// Server Component：在服务端经 lib/data.ts 读取数据并装配组件。
//   - 解析最新周 getLatestWeek()；无任何可用周次 → 渲染 EmptyState（Req 13.4）。
//   - 否则 loadReport(latest) 并用 Dashboard 装配完整仪表盘布局。
//
// 路由保护由 middleware.ts 统一处理（未认证重定向至 /login，Req 12.1），
// 因此此处无需再校验认证。lib/data.ts 为 server-only，仅在此服务端组件中导入。

import { Dashboard, EmptyState } from "@/components";
import { getLatestWeek, listAvailableWeeks, loadReport } from "@/lib/data";

// 每次请求都重新读取数据目录，新同步进来的周报无需重建即可展示（Req 15.3）。
export const dynamic = "force-dynamic";

export default async function Home() {
  const latest = await getLatestWeek();

  // 无任何可用周次数据 → 空态（不提供返回链接，因为根本没有数据）。
  if (latest === null) {
    return <EmptyState />;
  }

  const [report, weeks] = await Promise.all([
    loadReport(latest),
    listAvailableWeeks(),
  ]);

  // 理论上 latest 来自 listAvailableWeeks，文件应存在；若期间被删除则空态兜底。
  if (report === null) {
    return <EmptyState latestWeek={null} />;
  }

  return <Dashboard report={report} weeks={weeks} current={latest} />;
}
