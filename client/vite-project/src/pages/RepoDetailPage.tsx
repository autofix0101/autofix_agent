import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteRepo, getRepoById } from "../api/repos";
import Navbar from "../components/Navbar";
import DeleteConfirmDialog from "../components/DeleteConfirmDialog";
import type { RepoDetail } from "../types";

function MetaRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-3 border-b border-[#21262d] last:border-0">
      <dt className="w-40 shrink-0 text-sm text-[#6e7681]">{label}</dt>
      <dd className="text-sm text-[#c9d1d9] break-all">{value}</dd>
    </div>
  );
}

export default function RepoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [repo, setRepo] = useState<RepoDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!id) return;
    getRepoById(id)
      .then(setRepo)
      .catch((err) => setError(err.message ?? "Repository not found"))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDelete = async () => {
    if (!id) return;
    setIsDeleting(true);
    try {
      await deleteRepo(id);
      navigate("/repos", { replace: true });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to delete repository";
      setError(message);
      setIsDeleting(false);
      setShowConfirm(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0d1117] flex flex-col">
      <Navbar />

      <main className="flex-1 max-w-4xl w-full mx-auto px-6 py-8">
        {/* Back */}
        <button
          onClick={() => navigate("/repos")}
          className="flex items-center gap-1.5 text-sm text-[#8b949e] hover:text-[#c9d1d9] transition-colors mb-6 cursor-pointer"
        >
          <svg height="14" viewBox="0 0 16 16" width="14" fill="currentColor">
            <path d="M9.78 12.78a.75.75 0 01-1.06 0L4.47 8.53a.75.75 0 010-1.06l4.25-4.25a.75.75 0 011.06 1.06L6.06 8l3.72 3.72a.75.75 0 010 1.06z" />
          </svg>
          Back to repositories
        </button>

        {loading && (
          <div className="text-sm text-[#8b949e] text-center py-12">Loading…</div>
        )}

        {error && (
          <div className="text-sm text-[#f85149] text-center py-12">{error}</div>
        )}

        {!loading && !error && repo && (
          <>
            {/* Header */}
            <div className="flex items-start justify-between mb-6 gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h1 className="text-xl font-semibold text-[#c9d1d9] font-mono">
                    {repo.owner}/{repo.name}
                  </h1>
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
                <a
                  href={repo.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-[#58a6ff] hover:underline"
                >
                  {repo.html_url}
                </a>
              </div>

              <button
                onClick={() => setShowConfirm(true)}
                className="shrink-0 text-sm px-4 py-2 border border-[#da3633] text-[#f85149] rounded hover:bg-[#da3633] hover:text-white transition-colors cursor-pointer"
              >
                Delete
              </button>
            </div>

            {/* Details table */}
            <div className="border border-[#30363d] rounded-md px-5">
              <dl>
                <MetaRow label="Repository" value={<span className="font-mono">{repo.owner}/{repo.name}</span>} />
                <MetaRow label="Default branch" value={<span className="font-mono">{repo.default_branch}</span>} />
                <MetaRow label="Visibility" value={repo.is_private ? "Private" : "Public"} />
                <MetaRow
                  label="Clone URL"
                  value={
                    <span className="font-mono text-xs break-all">{repo.clone_url}</span>
                  }
                />
                <MetaRow
                  label="Last commit"
                  value={
                    repo.last_commit_sha ? (
                      <span className="font-mono text-xs">{repo.last_commit_sha}</span>
                    ) : (
                      <span className="text-[#6e7681]">—</span>
                    )
                  }
                />
                <MetaRow
                  label="Added on"
                  value={new Date(repo.created_at).toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                />
                <MetaRow
                  label="Last updated"
                  value={new Date(repo.updated_at).toLocaleDateString("en-US", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                />
                <MetaRow
                  label="GitHub repo ID"
                  value={<span className="font-mono text-xs text-[#6e7681]">{repo.github_repo_id}</span>}
                />
              </dl>
            </div>
          </>
        )}
      </main>

      {showConfirm && repo && (
        <DeleteConfirmDialog
          repoName={`${repo.owner}/${repo.name}`}
          onConfirm={handleDelete}
          onCancel={() => setShowConfirm(false)}
          isDeleting={isDeleting}
        />
      )}
    </div>
  );
}
