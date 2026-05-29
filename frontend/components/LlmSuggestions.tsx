// frontend/components/LlmSuggestions.tsx
//
// 自动建议（可选，LLM）——仅当 StructuredExport.llm_suggestions 非 null 时渲染
// 该区块；LLM 默认关闭，关闭时为 null，组件返回 null 不占位（Req 6.6 / 6.7）。
//
// Server Component；基础 Tailwind 结构，最终样式在任务 18.1 落地。

interface LlmSuggestionsProps {
  /** LLM 建议文本；关闭时为 null。 */
  suggestions: string | null;
}

export function LlmSuggestions({ suggestions }: LlmSuggestionsProps) {
  if (suggestions === null) {
    return null;
  }

  return (
    <section data-component="llm-suggestions" className="space-y-4">
      <h2 className="text-lg font-semibold">自动建议（可选，LLM）</h2>
      <p className="whitespace-pre-line text-sm text-gray-700">{suggestions}</p>
    </section>
  );
}

export default LlmSuggestions;
