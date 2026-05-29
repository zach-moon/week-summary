// frontend/components/format.ts
//
// 展示层共享的小工具（纯函数，无副作用），供各展示组件复用。
// 不含任何 IO，可安全在 Server / Client Component 中导入。

import type { ProjectDistribution } from "@/lib/types";

/** Python 聚合器保留的「未匹配任何配置仓库」桶（aggregate.py）。 */
export const UNMATCHED_DIR = "__unmatched__";

/** 「未归类」桶的中文展示名（与 Markdown 渲染器行为一致）。 */
export const UNMATCHED_LABEL = "未归类";

/**
 * 项目展示名：保留桶 `__unmatched__` 显示「未归类」；否则优先使用导出器派生的
 * 友好名 `project_name`，缺失时回退到 `project_dir`（Req 13.2）。
 */
export function projectLabel(
  entry: Pick<ProjectDistribution, "project_dir" | "project_name">,
): string {
  if (entry.project_dir === UNMATCHED_DIR) return UNMATCHED_LABEL;
  return entry.project_name?.trim() || entry.project_dir;
}
