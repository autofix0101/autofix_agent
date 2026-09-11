import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteRepo, getRepoById, getRepoSignals } from "../api/repos";
import DeleteConfirmDialog from "../components/DeleteConfirmDialog";
import SignalCard from "../components/SignalCard";
import type { RepoDetail, Signal } from "../types";

type Tab = "issues" | "ci";

function StatCard({
  label,
  value,
  icon,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  icon: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div
      style={{
        background: "#0a1020",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
        padding: "16px 18px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 7,
            background: "rgba(99,102,241,0.1)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {icon}
        </div>
        <span style={{ fontSize: "0.72rem", color: "#475569", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          {label}
        </span>
      </div>
      <div
        style={{
          fontSize: mono ? "0.8rem" : "0.9rem",
          color: "#f1f5f9",
          fontFamily: mono ? "monospace" : undefined,
          fontWeight: 500,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </div>
    </div>
  );
}

export default function RepoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [repo, setRepo] = useState<RepoDetail | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loadingRepo, setLoadingRepo] = useState(true);
  const [loadingSignals, setLoadingSignals] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("issues");

  useEffect(() => {
    if (!id) return;
    getRepoById(id)
      .then((data) => {
        setRepo(data);
        // Load signals right after repo loads
        setLoadingSignals(true);
        return getRepoSignals(id);
      })
      .then((data) => setSignals(data))
      .catch((err) => setError(err.message ?? "Failed to load repository"))
      .finally(() => {
        setLoadingRepo(false);
        setLoadingSignals(false);
      });
  }, [id]);

  // Poll signals every 30 s to catch updates
  useEffect(() => {
    if (!id) return;
    const interval = setInterval(() => {
      getRepoSignals(id)
        .then(setSignals)
        .catch(() => {/* silent */});
    }, 30_000);
    return () => clearInterval(interval);
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

  const issueSignals = signals.filter((s) => s.type === "github_issue");
  const ciSignals = signals.filter((s) => s.type === "ci_failure");

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      {/* Header */}
      <div
        style={{
          padding: "24px 32px",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
          flexShrink: 0,
        }}
      >
        {/* Breadcrumb */}
        <button
          onClick={() => navigate("/repos")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            background: "transparent",
            border: "none",
            color: "#475569",
            fontSize: "0.8rem",
            cursor: "pointer",
            padding: 0,
            marginBottom: 16,
            transition: "color 0.15s",
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "#94a3b8")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "#475569")}
        >
          <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
            <path d="M9.78 12.78a.75.75 0 01-1.06 0L4.47 8.53a.75.75 0 010-1.06l4.25-4.25a.75.75 0 011.06 1.06L6.06 8l3.72 3.72a.75.75 0 010 1.06z" />
          </svg>
          Repositories
        </button>

        {loadingRepo ? (
          <div
            style={{
              height: 32,
              width: 200,
              borderRadius: 8,
              background: "rgba(255,255,255,0.04)",
              animation: "pulse 1.5s ease-in-out infinite",
            }}
          />
        ) : repo ? (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              {/* Repo icon */}
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: "linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))",
                  border: "1px solid rgba(99,102,241,0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <svg width="20" height="20" viewBox="0 0 16 16" fill="#818cf8">
                  <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" />
                </svg>
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <h1
                    style={{
                      fontSize: "1.3rem",
                      fontWeight: 700,
                      color: "#f1f5f9",
                      fontFamily: "monospace",
                      letterSpacing: "-0.01em",
                    }}
                  >
                    {repo.owner}/{repo.name}
                  </h1>
                  <span
                    style={{
                      fontSize: "0.68rem",
                      padding: "2px 8px",
                      borderRadius: 999,
                      background: repo.is_private ? "rgba(100,116,139,0.15)" : "rgba(16,185,129,0.1)",
                      color: repo.is_private ? "#94a3b8" : "#34d399",
                      border: `1px solid ${repo.is_private ? "rgba(100,116,139,0.25)" : "rgba(16,185,129,0.25)"}`,
                      fontWeight: 600,
                    }}
                  >
                    {repo.is_private ? "Private" : "Public"}
                  </span>
                  <span
                    style={{
                      fontSize: "0.68rem",
                      padding: "2px 8px",
                      borderRadius: 999,
                      background: repo.github_webhook_id ? "rgba(16,185,129,0.1)" : "rgba(245,158,11,0.1)",
                      color: repo.github_webhook_id ? "#34d399" : "#fbbf24",
                      border: `1px solid ${repo.github_webhook_id ? "rgba(16,185,129,0.25)" : "rgba(245,158,11,0.25)"}`,
                      fontWeight: 600,
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        background: repo.github_webhook_id ? "#34d399" : "#fbbf24",
                        flexShrink: 0,
                      }}
                    />
                    {repo.github_webhook_id ? "Webhook active" : "No webhook"}
                  </span>
                </div>
                <a
                  href={repo.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: "0.78rem",
                    color: "#4f46e5",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    textDecoration: "none",
                    marginTop: 3,
                    transition: "color 0.15s",
                  }}
                  onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.color = "#818cf8")}
                  onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.color = "#4f46e5")}
                >
                  {repo.html_url}
                  <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor">
                    <path fillRule="evenodd" d="M10.604 1h4.146a.25.25 0 01.25.25v4.146a.25.25 0 01-.427.177L13.03 4.03 9.28 7.78a.75.75 0 01-1.06-1.06l3.75-3.75-1.543-1.543A.25.25 0 0110.604 1zM3.75 2A1.75 1.75 0 002 3.75v8.5c0 .966.784 1.75 1.75 1.75h8.5A1.75 1.75 0 0014 12.25v-3.5a.75.75 0 00-1.5 0v3.5a.25.25 0 01-.25.25h-8.5a.25.25 0 01-.25-.25v-8.5a.25.25 0 01.25-.25h3.5a.75.75 0 000-1.5h-3.5z" />
                  </svg>
                </a>
              </div>
            </div>

            {/* Delete button */}
            <button
              onClick={() => setShowConfirm(true)}
              style={{
                padding: "8px 16px",
                background: "transparent",
                border: "1px solid rgba(239,68,68,0.3)",
                borderRadius: 9,
                color: "#f87171",
                fontSize: "0.82rem",
                fontWeight: 500,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
                transition: "all 0.15s",
                flexShrink: 0,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "rgba(239,68,68,0.08)";
                (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(239,68,68,0.5)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(239,68,68,0.3)";
              }}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                <path d="M11 1.75V3h2.25a.75.75 0 010 1.5H2.75a.75.75 0 010-1.5H5V1.75C5 .784 5.784 0 6.75 0h2.5C10.216 0 11 .784 11 1.75zM4.496 6.675l.66 6.6a.25.25 0 00.249.225h5.19a.25.25 0 00.249-.225l.66-6.6a.75.75 0 011.492.149l-.66 6.6A1.748 1.748 0 0110.595 15h-5.19a1.75 1.75 0 01-1.741-1.575l-.66-6.6a.75.75 0 111.492-.15z" />
              </svg>
              Remove
            </button>
          </div>
        ) : null}

        {error && (
          <div
            style={{
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: 10,
              padding: "12px 16px",
              color: "#f87171",
              fontSize: "0.875rem",
              marginTop: 12,
            }}
          >
            {error}
          </div>
        )}
      </div>

      {/* Body */}
      {!loadingRepo && repo && (
        <div style={{ flex: 1, padding: "24px 32px", overflowY: "auto" }}>
          {/* Stats grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 12,
              marginBottom: 32,
            }}
          >
            <StatCard
              label="Branch"
              value={repo.default_branch}
              mono
              icon={
                <svg width="13" height="13" viewBox="0 0 16 16" fill="#818cf8">
                  <path fillRule="evenodd" d="M11.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122V6A2.5 2.5 0 019.5 8.5H6.75v1.378a2.251 2.251 0 11-1.5 0V2.5h-3a.75.75 0 000 1.5H3.5v9.25a.75.75 0 001.5 0V8.5H9.5A1 1 0 0010.5 7.5V5.372A2.25 2.25 0 019.5 3.25z" />
                </svg>
              }
            />
            <StatCard
              label="Last commit"
              value={repo.last_commit_sha ? repo.last_commit_sha.slice(0, 12) : "—"}
              mono
              icon={
                <svg width="13" height="13" viewBox="0 0 16 16" fill="#818cf8">
                  <path fillRule="evenodd" d="M10.5 7.75a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm1.43.75a4.002 4.002 0 01-7.86 0H.75a.75.75 0 110-1.5h3.32a4.001 4.001 0 017.86 0h3.32a.75.75 0 110 1.5h-3.32z" />
                </svg>
              }
            />
            <StatCard
              label="Added"
              value={formatDate(repo.created_at)}
              icon={
                <svg width="13" height="13" viewBox="0 0 16 16" fill="#818cf8">
                  <path fillRule="evenodd" d="M4.75 0a.75.75 0 01.75.75V2h5V.75a.75.75 0 011.5 0V2h1.25c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0113.25 16H2.75A1.75 1.75 0 011 14.25V3.75C1 2.784 1.784 2 2.75 2H4V.75A.75.75 0 014.75 0zm0 3.5h-2a.25.25 0 00-.25.25V6h11V3.75a.25.25 0 00-.25-.25h-2V5a.75.75 0 01-1.5 0v-1.5h-5V5a.75.75 0 01-1.5 0v-1.5zM2.5 7.5v6.75c0 .138.112.25.25.25h10.5a.25.25 0 00.25-.25V7.5h-11z" />
                </svg>
              }
            />
            <StatCard
              label="Signals"
              value={`${signals.length} total · ${issueSignals.length} issues · ${ciSignals.length} CI`}
              icon={
                <svg width="13" height="13" viewBox="0 0 16 16" fill="#818cf8">
                  <path d="M8 2c-.5 0-1 .15-1.4.45L1.4 6.5C1 6.85 1 7.25 1 7.7c0 .9.7 1.6 1.5 1.6h.1l.9 4.1c.1.4.5.6.9.6h7.1c.4 0 .8-.2.9-.6l.9-4.1h.1c.8 0 1.5-.7 1.5-1.6 0-.45 0-.85-.4-1.2L9.4 2.45C9 2.15 8.5 2 8 2z" />
                </svg>
              }
            />
          </div>

          {/* Clone URL */}
          <div
            style={{
              background: "#0a1020",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 10,
              padding: "12px 16px",
              marginBottom: 28,
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="#475569" style={{ flexShrink: 0 }}>
              <path fillRule="evenodd" d="M3.5 1.75a.25.25 0 01.25-.25h3a.75.75 0 000-1.5h-3A1.75 1.75 0 002 1.75v11.5c0 .966.784 1.75 1.75 1.75h8.5A1.75 1.75 0 0014 13.25v-8.5A1.75 1.75 0 0012.25 3h-3a.75.75 0 000 1.5h3a.25.25 0 01.25.25v8.5a.25.25 0 01-.25.25h-8.5a.25.25 0 01-.25-.25V1.75zM8.97 4.97a.75.75 0 011.06 1.06l-4.25 4.25a.75.75 0 01-1.06 0l-1.75-1.75a.75.75 0 011.06-1.06l1.22 1.22 3.72-3.72z" />
            </svg>
            <span style={{ fontSize: "0.72rem", color: "#475569", flexShrink: 0 }}>Clone URL</span>
            <code
              style={{
                fontSize: "0.78rem",
                color: "#64748b",
                fontFamily: "monospace",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                flex: 1,
              }}
            >
              {repo.clone_url}
            </code>
            <button
              onClick={() => navigator.clipboard.writeText(repo.clone_url)}
              style={{
                background: "transparent",
                border: "none",
                color: "#475569",
                cursor: "pointer",
                padding: 0,
                display: "flex",
                alignItems: "center",
                flexShrink: 0,
                transition: "color 0.15s",
              }}
              title="Copy to clipboard"
              onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "#94a3b8")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "#475569")}
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 010 1.5h-1.5a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-1.5a.75.75 0 011.5 0v1.5A1.75 1.75 0 019.25 16h-7.5A1.75 1.75 0 010 14.25v-7.5z" />
                <path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0114.25 11h-7.5A1.75 1.75 0 015 9.25v-7.5zm1.75-.25a.25.25 0 00-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 00.25-.25v-7.5a.25.25 0 00-.25-.25h-7.5z" />
              </svg>
            </button>
          </div>

          {/* Signals section */}
          <div>
            <h2
              style={{
                fontSize: "1rem",
                fontWeight: 700,
                color: "#f1f5f9",
                letterSpacing: "-0.01em",
                marginBottom: 16,
              }}
            >
              Signals
            </h2>

            {/* Tabs */}
            <div className="tab-strip">
              <button
                className={`tab-item${activeTab === "issues" ? " active" : ""}`}
                onClick={() => setActiveTab("issues")}
                style={{ background: "none", border: "none", cursor: "pointer" }}
              >
                Issues
                <span
                  style={{
                    marginLeft: 6,
                    fontSize: "0.68rem",
                    padding: "1px 6px",
                    borderRadius: 999,
                    background: "rgba(99,102,241,0.1)",
                    color: "#818cf8",
                  }}
                >
                  {issueSignals.length}
                </span>
              </button>
              <button
                className={`tab-item${activeTab === "ci" ? " active" : ""}`}
                onClick={() => setActiveTab("ci")}
                style={{ background: "none", border: "none", cursor: "pointer" }}
              >
                CI Failures
                <span
                  style={{
                    marginLeft: 6,
                    fontSize: "0.68rem",
                    padding: "1px 6px",
                    borderRadius: 999,
                    background: ciSignals.length > 0 ? "rgba(239,68,68,0.1)" : "rgba(100,116,139,0.1)",
                    color: ciSignals.length > 0 ? "#f87171" : "#64748b",
                  }}
                >
                  {ciSignals.length}
                </span>
              </button>
            </div>

            {/* Signal list */}
            {loadingSignals ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "40px 0" }}>
                <div
                  style={{
                    width: 22,
                    height: 22,
                    border: "2px solid rgba(99,102,241,0.2)",
                    borderTopColor: "#6366f1",
                    borderRadius: "50%",
                    animation: "spin 0.8s linear infinite",
                  }}
                />
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(activeTab === "issues" ? issueSignals : ciSignals).length === 0 ? (
                  <div
                    style={{
                      padding: "48px 0",
                      textAlign: "center",
                    }}
                  >
                    <div
                      style={{
                        width: 48,
                        height: 48,
                        borderRadius: 12,
                        background: "rgba(99,102,241,0.07)",
                        border: "1px solid rgba(99,102,241,0.15)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        margin: "0 auto 14px",
                      }}
                    >
                      {activeTab === "issues" ? (
                        <svg width="20" height="20" viewBox="0 0 16 16" fill="#475569">
                          <path d="M8 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" />
                          <path fillRule="evenodd" d="M8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z" />
                        </svg>
                      ) : (
                        <svg width="20" height="20" viewBox="0 0 16 16" fill="#475569">
                          <path fillRule="evenodd" d="M8.22 1.754a.25.25 0 00-.44 0L1.698 13.132a.25.25 0 00.22.368h12.164a.25.25 0 00.22-.368L8.22 1.754z" />
                        </svg>
                      )}
                    </div>
                    <p style={{ fontSize: "0.875rem", color: "#475569" }}>
                      No {activeTab === "issues" ? "issues" : "CI failures"} received yet
                    </p>
                    <p style={{ fontSize: "0.78rem", color: "#334155", marginTop: 4 }}>
                      {activeTab === "issues"
                        ? "New GitHub issues will appear here when webhooks fire."
                        : "Failed workflow runs will appear here when webhooks fire."}
                    </p>
                  </div>
                ) : (
                  (activeTab === "issues" ? issueSignals : ciSignals).map((signal) => (
                    <SignalCard key={signal.id} signal={signal} />
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      )}

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
