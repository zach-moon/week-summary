// frontend/components/CommitList.tsx
//
// 本周做了什么（commit）——按仓库分组展示带日期的提交标题（Req 13.2）。
// 消费 StructuredExport.repo_commits（RepoCommitGroup[]）。
//
// Server Component；基础 Tailwind 结构，样式后续在 18.1 替换。

import type { RepoCommitGroup } from "@/lib/types";

interface CommitListProps {
  repoCommits: RepoCommitGroup[];
}

export function CommitList({ repoCommits }: CommitListProps) {
  // 仅展示窗内有提交的仓库；全部为空时给出空提示。
  const groupsWithCommits = repoCommits.filter(
    (group) => group.commits.length > 0,
  );

  return (
    <section data-component="commit-list" className="space-y-4">
      <h2 className="text-lg font-semibold">本周做了什么（commit）</h2>

      {groupsWithCommits.length === 0 ? (
        <p className="text-sm text-gray-500">本周暂无提交记录。</p>
      ) : (
        <div className="space-y-5">
          {groupsWithCommits.map((group) => (
            <div
              key={group.repo_id}
              data-repo={group.repo_id}
              className="space-y-2"
            >
              <h3 className="text-sm font-semibold text-gray-700">
                {group.repo_id}
              </h3>
              <ul className="space-y-1">
                {group.commits.map((commit, index) => (
                  <li
                    key={`${commit.date}-${index}`}
                    className="flex gap-3 text-sm"
                  >
                    <time
                      dateTime={commit.date}
                      className="shrink-0 tabular-nums text-gray-500"
                    >
                      {commit.date}
                    </time>
                    <span>{commit.subject}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default CommitList;
