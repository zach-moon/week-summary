// frontend/components/CommitList.tsx
//
// 本周做了什么（CommitsBand）——按仓库分组展示带日期的提交标题（Req 13.2）。
// 依据 Claude Design mockup 落地（任务 18.1）：eyebrow「本周做了什么」+ band-title +
// 每个仓库一个 .proj 块（.proj-name mono + 次数）+ .cmts 列表（mono .cmt-date MM-DD
// + .cmt-subj）。
//
// 消费 StructuredExport.repo_commits（RepoCommitGroup[]）。
//
// 使用 Reveal（客户端动效组件）；本组件本身无状态，作为 Server Component 渲染。

import type { RepoCommitGroup } from "@/lib/types";

import { shortDate } from "./format";
import { Reveal } from "./motion";

interface CommitListProps {
  repoCommits: RepoCommitGroup[];
}

export function CommitList({ repoCommits }: CommitListProps) {
  // 仅展示窗内有提交的仓库；全部为空时给出空提示。
  const groups = repoCommits.filter((group) => group.commits.length > 0);

  return (
    <section className="band band-base" data-component="commit-list">
      <div className="wrap">
        <Reveal as="p" className="eyebrow">
          本周做了什么
        </Reveal>
        <Reveal as="h2" className="band-title">
          按项目展开的提交时间线
        </Reveal>

        {groups.length === 0 ? (
          <p className="empty-sub">本周暂无提交记录。</p>
        ) : (
          <div className="proj-list">
            {groups.map((group) => (
              <Reveal className="proj" key={group.repo_id}>
                <div className="proj-head">
                  <h3 className="proj-name">{group.repo_id}</h3>
                  <span className="proj-count">
                    {group.commits.length} 次提交
                  </span>
                </div>
                <ul className="cmts">
                  {group.commits.map((commit, index) => (
                    <li className="cmt" key={`${commit.date}-${index}`}>
                      <time className="cmt-date" dateTime={commit.date}>
                        {shortDate(commit.date)}
                      </time>
                      <span className="cmt-subj">{commit.subject}</span>
                    </li>
                  ))}
                </ul>
              </Reveal>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default CommitList;
