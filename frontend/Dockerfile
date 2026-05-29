# syntax=docker/dockerfile:1
#
# Next.js standalone 多阶段构建（deps -> builder -> runner），产出最小运行镜像。
# 依赖 next.config.js 的 output: "standalone"（Req 15.1）。
# standalone 输出不含 .next/static 与 public，需在 runner 阶段单独复制。
# 所有 secrets 经运行时环境变量注入，绝不写入镜像（Req 15.4）。

# 1) deps —— 仅安装依赖，最大化利用层缓存
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# 2) builder —— 复用 deps 的 node_modules，构建 standalone 产物
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# 3) runner —— 最小运行时，非 root 用户
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# 数据卷默认挂载到 /data（docker-compose 中以只读方式挂载，Req 15.2/15.3）
ENV DATA_DIR=/data

# 创建非 root 用户/组并以其身份运行（容器最小权限）
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs

# standalone 产物（含精简版 node_modules 与 server.js）复制到工作目录根
COPY --from=builder /app/.next/standalone ./
# 静态资源与 public 资源在 standalone 输出中缺省，需单独复制
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER nextjs
EXPOSE 3000
# standalone 输出自带 server.js 作为入口
CMD ["node", "server.js"]
