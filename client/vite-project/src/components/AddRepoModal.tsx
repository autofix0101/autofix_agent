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
  const [search, setSearch] = useState("");
  const [webhookWarnings, setWebhookWarnings] = useState<Record<number, string>>({});

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
      const { result, webhookSetupError } = await addRepo({
        githubRepoId: repo.githubRepoId,
        name: repo.name,
        owner: repo.owner,
        cloneUrl: repo.cloneUrl,
        htmlUrl: repo.htmlUrl,
        defaultBranch: repo.defaultBranch,
        isPrivate: repo.isPrivate,
      });
      setAddedIds((prev) => new Set(prev).add(repo.githubRepoId));
      if (webhookSetupError) {
        setWebhookWarnings((prev) => ({ ...prev, [repo.githubRepoId]: webhookSetupError }));
      }
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

  const filtered = githubRepos.filter(
    (r) =>
      search.trim() === "" ||
      `${r.owner}/${r.name}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px 16px",
      }}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.7)",
          backdropFilter: "blur(4px)",
        }}
      />

      {/* Modal */}
      <div
        className="animate-slide-up"
        style={{
          position: "relative",
          background: "#0d1526",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 18,
          width: "100%",
          maxWidth: 580,
          maxHeight: "80vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 24px 80px rgba(0,0,0,0.7)",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "20px 22px 16px",
            borderBottom: "1px solid rgba(255,255,255,0.06)",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div>
              <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "#f1f5f9", marginBottom: 2 }}>
                Connect a repository
              </h2>
              <p style={{ fontSize: "0.78rem", color: "#475569" }}>
                Select a GitHub repository to monitor with Autofix
              </p>
            </div>
            <button
              onClick={onClose}
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 8,
                width: 32,
                height: 32,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#64748b",
                cursor: "pointer",
                transition: "all 0.15s",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.08)";
                (e.currentTarget as HTMLButtonElement).style.color = "#f1f5f9";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.05)";
                (e.currentTarget as HTMLButtonElement).style.color = "#64748b";
              }}
              aria-label="Close"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
              </svg>
            </button>
          </div>

          {/* Search */}
          <div style={{ position: "relative" }}>
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="#475569"
              style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)" }}
            >
              <path d="M10.68 11.74a6 6 0 01-7.922-8.982 6 6 0 018.982 7.922l3.04 3.04a.749.749 0 11-1.06 1.06l-3.04-3.04zm-5.68.26a4.5 4.5 0 100-9 4.5 4.5 0 000 9z" />
            </svg>
            <input
              type="text"
              placeholder="Search repositories..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: "100%",
                padding: "9px 12px 9px 34px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 9,
                color: "#f1f5f9",
                fontSize: "0.85rem",
                outline: "none",
                transition: "border-color 0.15s",
              }}
              onFocus={(e) => ((e.currentTarget as HTMLInputElement).style.borderColor = "rgba(99,102,241,0.5)")}
              onBlur={(e) => ((e.currentTarget as HTMLInputElement).style.borderColor = "rgba(255,255,255,0.08)")}
            />
          </div>
        </div>

        {/* Body */}
        <div style={{ overflowY: "auto", flex: 1 }}>
          {loading && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, padding: "48px 0" }}>
              <div
                style={{
                  width: 18,
                  height: 18,
                  border: "2px solid rgba(99,102,241,0.2)",
                  borderTopColor: "#6366f1",
                  borderRadius: "50%",
                  animation: "spin 0.8s linear infinite",
                }}
              />
              <span style={{ fontSize: "0.85rem", color: "#475569" }}>Loading your GitHub repositories…</span>
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
          )}

          {fetchError && (
            <div
              style={{
                margin: 16,
                padding: "12px 16px",
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.25)",
                borderRadius: 10,
                color: "#f87171",
                fontSize: "0.85rem",
              }}
            >
              {fetchError}
            </div>
          )}

          {!loading && !fetchError && filtered.length === 0 && (
            <div style={{ padding: "48px 0", textAlign: "center" }}>
              <p style={{ fontSize: "0.875rem", color: "#475569" }}>
                {search ? "No repositories match your search." : "No repositories found on your GitHub account."}
              </p>
            </div>
          )}

          {!loading && !fetchError && filtered.length > 0 && (
            <div style={{ padding: "8px 0" }}>
              {filtered.map((repo) => {
                const added = isAdded(repo.githubRepoId);
                const adding = addingId === repo.githubRepoId;
                const errMsg = errors[repo.githubRepoId];
                const warnMsg = webhookWarnings[repo.githubRepoId];

                return (
                  <div
                    key={repo.githubRepoId}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "12px 20px",
                      borderBottom: "1px solid rgba(255,255,255,0.04)",
                      transition: "background 0.15s",
                    }}
                    onMouseEnter={(e) => ((e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.02)")}
                    onMouseLeave={(e) => ((e.currentTarget as HTMLDivElement).style.background = "transparent")}
                  >
                    {/* Icon */}
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 9,
                        background: "rgba(99,102,241,0.08)",
                        border: "1px solid rgba(99,102,241,0.15)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                      }}
                    >
                      <svg width="15" height="15" viewBox="0 0 16 16" fill="#818cf8">
                        <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" />
                      </svg>
                    </div>

                    {/* Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                        <span
                          style={{
                            fontSize: "0.875rem",
                            fontWeight: 500,
                            color: "#f1f5f9",
                            fontFamily: "monospace",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {repo.owner}/{repo.name}
                        </span>
                        <span
                          style={{
                            fontSize: "0.68rem",
                            padding: "1px 6px",
                            borderRadius: 999,
                            background: repo.isPrivate ? "rgba(100,116,139,0.15)" : "rgba(16,185,129,0.1)",
                            color: repo.isPrivate ? "#94a3b8" : "#34d399",
                            border: `1px solid ${repo.isPrivate ? "rgba(100,116,139,0.25)" : "rgba(16,185,129,0.25)"}`,
                            flexShrink: 0,
                          }}
                        >
                          {repo.isPrivate ? "Private" : "Public"}
                        </span>
                      </div>
                      <div style={{ fontSize: "0.72rem", color: "#475569", fontFamily: "monospace" }}>
                        {repo.defaultBranch}
                      </div>
                      {errMsg && (
                        <div style={{ fontSize: "0.72rem", color: "#f87171", marginTop: 3 }}>{errMsg}</div>
                      )}
                      {warnMsg && (
                        <div
                          style={{
                            fontSize: "0.7rem",
                            color: "#fbbf24",
                            marginTop: 4,
                            padding: "5px 8px",
                            background: "rgba(245,158,11,0.08)",
                            borderRadius: 6,
                            border: "1px solid rgba(245,158,11,0.2)",
                          }}
                        >
                          ⚠ Webhook setup failed — signals won't arrive automatically.
                        </div>
                      )}
                    </div>

                    {/* Add button */}
                    <button
                      onClick={() => handleAdd(repo)}
                      disabled={added || adding}
                      style={{
                        padding: "7px 14px",
                        borderRadius: 8,
                        border: added
                          ? "1px solid rgba(16,185,129,0.3)"
                          : adding
                          ? "1px solid rgba(99,102,241,0.25)"
                          : "1px solid rgba(99,102,241,0.4)",
                        background: added
                          ? "rgba(16,185,129,0.08)"
                          : adding
                          ? "rgba(99,102,241,0.08)"
                          : "rgba(99,102,241,0.12)",
                        color: added ? "#34d399" : adding ? "#818cf8" : "#a78bfa",
                        fontSize: "0.78rem",
                        fontWeight: 600,
                        cursor: added || adding ? "default" : "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 5,
                        flexShrink: 0,
                        transition: "all 0.15s",
                      }}
                    >
                      {adding ? (
                        <>
                          <div
                            style={{
                              width: 10,
                              height: 10,
                              border: "1.5px solid rgba(129,140,248,0.3)",
                              borderTopColor: "#818cf8",
                              borderRadius: "50%",
                              animation: "spin 0.8s linear infinite",
                            }}
                          />
                          Adding…
                        </>
                      ) : added ? (
                        <>
                          <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
                          </svg>
                          Added
                        </>
                      ) : (
                        "Connect"
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
