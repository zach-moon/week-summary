import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Heliora — 开发周报",
  description: "把每周散落在各个仓库里的提交与思考，安静地汇成一处。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
