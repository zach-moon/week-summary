import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import path from "node:path";

// 纯逻辑（pure-logic）属性测试（*.test.ts）不渲染 React、不需要 DOM，故用 "node" 环境。
// 组件 / 快照测试（*.test.tsx，任务 17.3）通过 react-dom/server 的
// renderToStaticMarkup 在 node 下做服务端渲染，断言生成的静态 HTML 字符串；
// 同样无需 jsdom。
//
// 把 "@/*" 路径别名解析到 frontend 根目录，使测试中的 `@/lib/...`、`@/components/...`
// 导入与 tsconfig.json 的 paths 设置保持一致。
const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": rootDir,
    },
  },
  // 项目组件按 Next.js 约定使用 automatic JSX runtime（不显式 import React）；
  // 显式声明 esbuild 的 automatic 运行时，确保 .tsx 组件与测试文件被正确转换
  // （覆盖 tsconfig 的 "jsx": "preserve"）。
  esbuild: {
    jsx: "automatic",
  },
  test: {
    environment: "node",
    // 同时纳入既有 .test.ts 与新增的 .test.tsx（向后兼容：.test.ts 仍匹配）。
    include: ["__tests__/**/*.test.{ts,tsx}"],
  },
});
