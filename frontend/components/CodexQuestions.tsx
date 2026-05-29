// frontend/components/CodexQuestions.tsx
//
// 我提了什么关键问题（codex）——按项目分组展示 codex 会话的主题（themes）
// 与关键问题（key_questions），并附该组会话数（Req 13.2）。
// 消费 StructuredExport.repo_codex（RepoCodexGroup[]）。
//
// 隐私边界：repo_codex 仅含摘要化的 themes / key_questions，不含原始对话全文。
//
// Server Component；基础 Tailwind 结构，最终样式在任务 18.1 落地。

import type { RepoCodexGroup } from "@/lib/types";

import { projectLabel } from "./format";

interface CodexQuestionsProps {
  repoCodex: RepoCodexGroup[];
}

export function CodexQuestions({ repoCodex }: CodexQuestionsProps) {
  // 仅展示存在主题或关键问题的分组；全部为空时给出空提示。
  const groups = repoCodex.filter(
    (group) => group.themes.length > 0 || group.key_questions.length > 0,
  );

  return (
    <section data-component="codex-questions" className="space-y-4">
      <h2 className="text-lg font-semibold">我提了什么关键问题（codex）</h2>

      {groups.length === 0 ? (
        <p className="text-sm text-gray-500">本周暂无 codex 关键问题。</p>
      ) : (
        <div className="space-y-5">
          {groups.map((group) => (
            <div
              key={group.repo_id}
              data-repo={group.repo_id}
              className="space-y-2"
            >
              <div className="flex items-baseline justify-between gap-4">
                <h3 className="text-sm font-semibold text-gray-700">
                  {/* repo_id 实为 project_dir；复用 projectLabel 处理 __unmatched__。 */}
                  {projectLabel({
                    project_dir: group.repo_id,
                    project_name: group.repo_id,
                  })}
                </h3>
                <span className="shrink-0 text-sm text-gray-500">
                  {group.session_count} sessions
                </span>
              </div>

              {group.themes.length > 0 && (
                <ul className="flex flex-wrap gap-2" data-section="themes">
                  {group.themes.map((theme, index) => (
                    <li
                      key={`${theme}-${index}`}
                      className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
                    >
                      {theme}
                    </li>
                  ))}
                </ul>
              )}

              {group.key_questions.length > 0 && (
                <ul
                  className="list-disc space-y-1 pl-5 text-sm"
                  data-section="key-questions"
                >
                  {group.key_questions.map((question, index) => (
                    <li key={`${index}-${question}`}>{question}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default CodexQuestions;
