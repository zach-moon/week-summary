/** @type {import('next').NextConfig} */
const nextConfig = {
  // 最小化镜像：standalone 输出仅含运行所需文件（与容器化任务 20.1 一致）。
  output: "standalone",
};

module.exports = nextConfig;
