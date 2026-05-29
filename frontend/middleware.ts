// 路由保护：除认证路由 / 登录页 / 未授权页 / 静态资源外，所有路由都要求已认证。
// 未认证访问受保护页时，Auth.js middleware 会重定向到 pages.signIn（"/login"，Req 12.1）。
export { auth as middleware } from "@/lib/auth";

export const config = {
  // 排除：api/auth（OAuth 端点）、login（登录页）、unauthorized（无权限页）、
  // _next（构建产物）、favicon（站点图标）。其余全部受保护。
  matcher: ["/((?!api/auth|login|unauthorized|_next|favicon).*)"],
};
