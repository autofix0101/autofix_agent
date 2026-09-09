import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getRepos } from "../api/repos";
import Navbar from "../components/Navbar";
import AddRepoModal from "../components/AddRepoModal";
import type { Repo } from "../types";

export default function ReposPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    getRepos()
      .then(setRepos)
      .catch((err) => setError(err.message ?? "Failed to load repositories"))
      .finally(() => setLoading(false));
  }, []);

  const handleRepoAdded = (newRepo: Repo) => {
    setRepos((prev) => {
      // avoid duplicates if already present
      if (prev.some((r) => r.id === newRepo.id)) return prev;
      return [newRepo, ...prev];
    });
  };

  return (
    <div className="min-h-screen bg-[#0d1117] flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-8">
        {/* Page header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-semibold text-[#c9d1d9]">Repositories</h1>
          <button
            onClick={() => setModalOpen(true)}
            className="text-sm px-4 py-2 bg-[#238636] hover:bg-[#2ea043] text-white rounded transition-colors cursor-pointer"
          >
            + Add repository
          </button>
        </div>

        {/* Content */}
        {loading && (
          <div className="text-sm text-[#8b949e] py-12 text-center">Loading repositories…</div>
        )}

        {error && (
          <div className="text-sm text-[#f85149] py-12 text-center">{error}</div>
        )}

        {!loading && !error && repos.length === 0 && (
          <div className="border border-[#30363d] rounded-md py-16 text-center">
            <p className="text-[#8b949e] text-sm mb-3">No repositories added yet.</p>
            <button
              onClick={() => setModalOpen(true)}
              className="text-sm text-[#58a6ff] hover:underline cursor-pointer"
            >
              Add your first repository
            </button>
          </div>
        )}

        {!loading && !error && repos.length > 0 && (
          <div className="border border-[#30363d] rounded-md overflow-hidden">
            <ul className="divide-y divide-[#21262d]">
              {repos.map((repo) => (
                <li
                  key={repo.id}
                  onClick={() => navigate(`/repos/${repo.id}`)}
                  className="px-5 py-4 flex items-center gap-4 cursor-pointer hover:bg-[#161b22] transition-colors group"
                >
                  {/* Repo icon */}
                  <svg
                    className="shrink-0 text-[#6e7681] group-hover:text-[#8b949e] transition-colors"
                    height="18"
                    viewBox="0 0 16 16"
                    width="18"
                    aria-hidden="true"
                    fill="currentColor"
                  >
                    <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" />
                  </svg>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-[#58a6ff] font-mono group-hover:underline">
                        {repo.owner}/{repo.name}
                      </span>
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded border ${
                          repo.is_private
                            ? "border-[#30363d] text-[#8b949e]"
                            : "border-[#21262d] text-[#6e7681]"
                        }`}
                      >
                        {repo.is_private ? "Private" : "Public"}
                      </span>
                    </div>
                    <div className="text-xs text-[#6e7681] mt-0.5">
                      branch:{" "}
                      <span className="font-mono text-[#8b949e]">{repo.default_branch}</span>
                    </div>
                  </div>

                  {/* Chevron */}
                  <svg
                    className="shrink-0 text-[#30363d] group-hover:text-[#6e7681] transition-colors"
                    height="16"
                    viewBox="0 0 16 16"
                    width="16"
                    fill="currentColor"
                  >
                    <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z" />
                  </svg>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>

      {modalOpen && (
        <AddRepoModal
          existingRepos={repos}
          onClose={() => setModalOpen(false)}
          onAdded={handleRepoAdded}
        />
      )}
    </div>
  );
}
