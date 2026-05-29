// frontend/components/LlmSuggestions.tsx
//
// 自动建议（SuggestionBand）——仅当 StructuredExport.llm_suggestions 非空时渲染该
// 全幅深色沉浸段（Req 6.6 / 6.7）。依据 Claude Design mockup 落地（任务 18.1）：
// .band-dark + 辉光 .dark-glow + eyebrow「这一周的复盘」+ 大字 .suggest。
//
// LLM 默认关闭，关闭时为 null（或空串），组件返回 null 不占位。
//
// 使用 Reveal（客户端动效组件）；本组件本身无状态。

import { Reveal } from "./motion";

interface LlmSuggestionsProps {
  /** LLM 建议文本；关闭时为 null。 */
  suggestions: string | null;
}

export function LlmSuggestions({ suggestions }: LlmSuggestionsProps) {
  // null 或空串都不渲染（CLI 在 LLM 关闭时可能输出 null；mockup 数据用空串占位）。
  if (!suggestions) {
    return null;
  }

  return (
    <section className="band band-dark" data-component="llm-suggestions">
      <span className="dark-glow" aria-hidden="true" />
      <div className="wrap">
        <Reveal as="p" className="eyebrow on-dark">
          这一周的复盘
        </Reveal>
        <Reveal as="p" className="suggest" delay={80}>
          {suggestions}
        </Reveal>
      </div>
    </section>
  );
}

export default LlmSuggestions;
