import { useEffect, useState } from "react";
import { getGithubRepos } from "../api/githubRepos";
import { addRepo } from "../api/repos";
import type { GithubRepo, Repo } from "../types";

interface Props {
  existingRepos: Repo[];
  onClose: () => void;
  onAdded: (repo: Repo) => void;
}

export default function AddRepoModal({ existingRepos, onClose, onAdded }: Props) {
  const [githubRepos, setGithubRepos] = useState<GithubRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [addingId, setAddingId] = useState<number | null>(null);
  const [addedIds, setAddedIds] = useState<Set<number>>(new Set());
  const [errors, setErrors] = useState<Record<number, string>>({});

  const existingGithubIds = new Set(existingRepos.map((r) => Number(r.github_repo_id)));

  useEffect(() => {
    getGithubRepos()
      .then(({ repos }) => setGithubRepos(repos))
      .catch((err) => setFetchError(err.message ?? "Failed to fetch GitHub repositories"))
      .finally(() => setLoading(false));
  }, []);

  const handleAdd = async (repo: GithubRepo) => {
    setAddingId(repo.githubRepoId);
    setErrors((prev) => ({ ...prev, [repo.githubRepoId]: "" }));
    try {
      const { result } = await addRepo({
        githubRepoId: repo.githubRepoId,
        name: repo.name,
        owner: repo.owner,
        cloneUrl: repo.cloneUrl,
        htmlUrl: repo.htmlUrl,
        defaultBranch: repo.defaultBranch,
        isPrivate: repo.isPrivate,
      });
      setAddedIds((prev) => new Set(prev).add(repo.githubRepoId));
      onAdded({
        id: result.id,
        github_repo_id: String(result.github_repo_id),
        name: result.name,
        owner: result.owner,
        is_private: result.is_private,
        default_branch: result.default_branch,
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to add repository";
      setErrors((prev) => ({ ...prev, [repo.githubRepoId]: message }));
    } finally {
      setAddingId(null);
    }
  };

  const isAdded = (id: number) => existingGithubIds.has(id) || addedIds.has(id);

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center pt-16 px-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-[#161b22] border border-[#30363d] rounded-md w-full max-w-2xl shadow-2xl flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#30363d]">
          <h2 className="text-[#c9d1d9] font-semibold">Add a repository</h2>
          <button
            onClick={onClose}
            className="text-[#8b949e] hover:text-[#c9d1d9] transition-colors text-lg leading-none cursor-pointer"
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1">
          {loading && (
            <div className="p-8 text-center text-sm text-[#8b949e]">
              Loading your GitHub repositories…
            </div>
          )}

          {fetchError && (
            <div className="p-8 text-center text-sm text-[#f85149]">{fetchError}</div>
          )}

          {!loading && !fetchError && githubRepos.length === 0 && (
            <div className="p-8 text-center text-sm text-[#8b949e]">
              No repositories found on your GitHub account.
            </div>
          )}

          {!loading && !fetchError && githubRepos.length > 0 && (
            <ul className="divide-y divide-[#21262d]">
              {githubRepos.map((repo) => {
                const added = isAdded(repo.githubRepoId);
                const adding = addingId === repo.githubRepoId;
                const errMsg = errors[repo.githubRepoId];

                return (
                  <li key={repo.githubRepoId} className="px-5 py-3 flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-[#c9d1d9] font-mono">
                          {repo.owner}/{repo.name}
                        </span>
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded border ${
                            repo.isPrivate
                              ? "border-[#30363d] text-[#8b949e]"
                              : "border-[#21262d] text-[#6e7681]"
                          }`}
                        >
                          {repo.isPrivate ? "Private" : "Public"}
                        </span>
                      </div>
                      <div className="text-xs text-[#6e7681] mt-0.5">
                        branch: <span className="font-mono">{repo.defaultBranch}</span>
                      </div>
                      {errMsg && (
                        <div className="text-xs text-[#f85149] mt-1">{errMsg}</div>
                      )}
                    </div>

                    <button
                      onClick={() => handleAdd(repo)}
                      disabled={added || adding}
                      className={`text-xs px-3 py-1.5 rounded border transition-colors shrink-0 cursor-pointer ${
                        added
                          ? "border-[#21262d] text-[#6e7681] cursor-default"
                          : adding
                          ? "border-[#30363d] text-[#8b949e] opacity-60"
                          : "border-[#238636] text-[#3fb950] hover:bg-[#238636] hover:text-white"
                      }`}
                    >
                      {added ? "Added" : adding ? "Adding…" : "Add"}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
