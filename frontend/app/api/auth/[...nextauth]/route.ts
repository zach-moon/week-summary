// Auth.js 路由处理器（令牌交换 / OAuth 回调），由 lib/auth.ts 统一配置导出。
// 该 catch-all 路由承载 GitHub 授权码流程的全部端点（Req 12.1 / 12.2）。
import { handlers } from "@/lib/auth";

export const { GET, POST } = handlers;
