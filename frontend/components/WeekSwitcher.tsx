"use client";

// frontend/components/WeekSwitcher.tsx
//
// 周切换器（week switcher）——存在多周数据时提供按周切换入口（Req 13.3）。
// 依据 Claude Design mockup 的 .wsw 落地（任务 18.1）：上一周 / 下一周 chevron +
// 中心标签（mono report_identifier）+ 下拉菜单列出全部周次，高亮当前周。
//
// 外部 props 契约保持不变：`weeks: string[]`（来自 listAvailableWeeks，已降序排列，
// 最新周在前）与 `current: string`（当前展示的 Report_Identifier）。导航经 next/link
// 跳转 /week/[id]。mockup 中的日期范围与数据点需要更多字段（page 未提供），
// 这里以 id + 当前高亮呈现，保持在 prop 契约内。
//
// 客户端组件：含下拉开合状态与点击外部关闭逻辑。

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Caret, Chevron } from "./motion";

interface WeekSwitcherProps {
  weeks: string[];
  current: string;
}

export function WeekSwitcher({ weeks, current }: WeekSwitcherProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (weeks.length === 0) {
    return null;
  }

  // weeks 降序（最新在前）：index 越小越新。
  const index = weeks.indexOf(current);
  // 「下一周」= 更新的一周（index-1）；「上一周」= 更早的一周（index+1）。
  const newer = index > 0 ? weeks[index - 1] : null;
  const older = index >= 0 && index < weeks.length - 1 ? weeks[index + 1] : null;

  return (
    <div className="wsw" ref={ref} data-component="week-switcher" aria-label="周切换">
      {older ? (
        <Link className="wsw-nav" href={`/week/${older}`} aria-label="上一周">
          <Chevron dir="left" />
        </Link>
      ) : (
        <span className="wsw-nav disabled" aria-hidden="true">
          <Chevron dir="left" />
        </span>
      )}

      <button
        type="button"
        className="wsw-label"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <span className="wsw-id">{current}</span>
        <span className={"wsw-caret " + (open ? "up" : "")}>
          <Caret />
        </span>
      </button>

      {newer ? (
        <Link className="wsw-nav" href={`/week/${newer}`} aria-label="下一周">
          <Chevron dir="right" />
        </Link>
      ) : (
        <span className="wsw-nav disabled" aria-hidden="true">
          <Chevron dir="right" />
        </span>
      )}

      {open && (
        <div className="wsw-menu" role="menu">
          {weeks.map((week) => {
            const isCurrent = week === current;
            return (
              <Link
                key={week}
                href={`/week/${week}`}
                role="menuitem"
                data-week={week}
                aria-current={isCurrent ? "page" : undefined}
                className={"wsw-item " + (isCurrent ? "on" : "")}
                onClick={() => setOpen(false)}
              >
                <span className="wsw-item-id">{week}</span>
                <span className="wsw-item-dot" />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default WeekSwitcher;
