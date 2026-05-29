// frontend/components/CodexQuestions.tsx
//
// 我提了什么关键问题（CodexBand）——按项目分组展示 codex 会话的主题（themes）与
// 关键问题（key_questions），并附该组会话数（Req 13.2）。依据 Claude Design mockup
// 落地（任务 18.1）：eyebrow + band-title + 每组 .cx 块（mono name + session_count +
// .tags chips + .qs 列表，关键问题前带 “ 引号标记）。
//
// 消费 StructuredExport.repo_codex（RepoCodexGroup[]）。
// 隐私边界：repo_codex 仅含摘要化的 themes / key_questions，不含原始对话全文。
//
// 使用 Reveal（客户端动效组件）；本组件本身无状态，作为 Server Component 渲染。

import type { RepoCodexGroup } from "@/lib/types";

import { projectLabel } from "./format";
import { Reveal } from "./motion";

interface CodexQuestionsProps {
  repoCodex: RepoCodexGroup[];
}

export function CodexQuestions({ repoCodex }: CodexQuestionsProps) {
  // 仅展示存在主题或关键问题的分组；全部为空时给出空提示。
  const groups = repoCodex.filter(
    (group) => group.themes.length > 0 || group.key_questions.length > 0,
  );

  return (
    <section className="band band-alt" data-component="codex-questions">
      <div className="wrap">
        <Reveal as="p" className="eyebrow">
          我提了什么关键问题
        </Reveal>
        <Reveal as="h2" className="band-title">
          Codex 上的思考轨迹
        </Reveal>

        {groups.length === 0 ? (
          <p className="empty-sub">本周暂无 codex 关键问题。</p>
        ) : (
          <div className="codex-list">
            {groups.map((group) => (
              <Reveal className="cx" key={group.repo_id} data-repo={group.repo_id}>
                <div className="cx-head">
                  <h3 className="proj-name">
                    {/* repo_id 实为 project_dir；复用 projectLabel 处理 __unmatched__。 */}
                    {projectLabel({
                      project_dir: group.repo_id,
                      project_name: group.repo_id,
                    })}
                  </h3>
                  <span className="proj-count">{group.session_count} 个会话</span>
                </div>

                {group.themes.length > 0 && (
                  <div className="tags" data-section="themes">
                    {group.themes.map((theme, index) => (
                      <span className="tag" key={`${theme}-${index}`}>
                        {theme}
                      </span>
                    ))}
                  </div>
                )}

                {group.key_questions.length > 0 && (
                  <ul className="qs" data-section="key-questions">
                    {group.key_questions.map((question, index) => (
                      <li className="q" key={`${index}-${question}`}>
                        <span className="q-mark" aria-hidden="true">
                          &ldquo;
                        </span>
                        {question}
                      </li>
                    ))}
                  </ul>
                )}
              </Reveal>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default CodexQuestions;
