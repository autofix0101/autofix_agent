import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { getRepos } from "../api/repos";
import AddRepoModal from "../components/AddRepoModal";
import ToastContainer from "../components/Toast";
import { useToast } from "../hooks/useToast";
import type { Repo, SignalEvent } from "../types";

function RepoCard({
  repo,
  onClick,
  isAlerted,
}: {
  repo: Repo;
  onClick: () => void;
  isAlerted: boolean;
}) {
  return (
    <div
      onClick={onClick}
      className={isAlerted ? "animate-pulse-glow" : ""}
      style={{
        background: "#0d1526",
        border: `1px solid ${isAlerted ? "rgba(245,158,11,0.5)" : "rgba(255,255,255,0.06)"}`,
        borderRadius: 14,
        padding: "20px",
        cursor: "pointer",
        transition: "all 0.2s",
        position: "relative",
        overflow: "hidden",
      }}
      onMouseEnter={(e) => {
        if (!isAlerted) {
          (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(99,102,241,0.4)";
          (e.currentTarget as HTMLDivElement).style.background = "#111c35";
        }
      }}
      onMouseLeave={(e) => {
        if (!isAlerted) {
          (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.06)";
          (e.currentTarget as HTMLDivElement).style.background = "#0d1526";
        }
      }}
    >
      {/* Gradient top accent */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 2,
          background: isAlerted
            ? "linear-gradient(90deg, #f59e0b, #fbbf24)"
            : "linear-gradient(90deg, #6366f1, #8b5cf6)",
          opacity: isAlerted ? 1 : 0.5,
          borderRadius: "14px 14px 0 0",
        }}
      />

      {/* Alert badge */}
      {isAlerted && (
        <div
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "#f59e0b",
            boxShadow: "0 0 8px rgba(245,158,11,0.6)",
          }}
        />
      )}

      {/* Repo icon + name */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 14 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 9,
            background: isAlerted ? "rgba(245,158,11,0.12)" : "rgba(99,102,241,0.12)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill={isAlerted ? "#fbbf24" : "#818cf8"}>
            <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" />
          </svg>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: "0.9rem",
              fontWeight: 600,
              color: "#f1f5f9",
              fontFamily: "monospace",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              marginBottom: 4,
            }}
          >
            {repo.owner}/{repo.name}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                fontSize: "0.7rem",
                padding: "2px 7px",
                borderRadius: 999,
                background: repo.is_private ? "rgba(100,116,139,0.15)" : "rgba(16,185,129,0.1)",
                color: repo.is_private ? "#94a3b8" : "#34d399",
                border: `1px solid ${repo.is_private ? "rgba(100,116,139,0.25)" : "rgba(16,185,129,0.25)"}`,
                fontWeight: 500,
              }}
            >
              {repo.is_private ? "Private" : "Public"}
            </span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: "1px solid rgba(255,255,255,0.05)",
          paddingTop: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="#475569">
            <path fillRule="evenodd" d="M11.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122V6A2.5 2.5 0 019.5 8.5H6.75v1.378a2.251 2.251 0 11-1.5 0V2.5h-3a.75.75 0 000 1.5H3.5v9.25a.75.75 0 001.5 0V8.5H9.5A1 1 0 0010.5 7.5V5.372A2.25 2.25 0 019.5 3.25z" />
          </svg>
          <span style={{ fontSize: "0.72rem", color: "#475569", fontFamily: "monospace" }}>
            {repo.default_branch}
          </span>
        </div>

        {isAlerted && (
          <span
            style={{
              fontSize: "0.68rem",
              fontWeight: 600,
              color: "#f59e0b",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 2c-.5 0-1 .15-1.4.45L1.4 6.5C1 6.85 1 7.25 1 7.7c0 .9.7 1.6 1.5 1.6h.1l.9 4.1c.1.4.5.6.9.6h7.1c.4 0 .8-.2.9-.6l.9-4.1h.1c.8 0 1.5-.7 1.5-1.6 0-.45 0-.85-.4-1.2L9.4 2.45C9 2.15 8.5 2 8 2z" />
            </svg>
            New signal
          </span>
        )}

        <svg width="14" height="14" viewBox="0 0 16 16" fill="#475569">
          <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z" />
        </svg>
      </div>
    </div>
  );
}

export default function ReposPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [alertedRepoIds, setAlertedRepoIds] = useState<Set<string>>(new Set());
  const { toasts, addToast, dismiss } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    getRepos()
      .then(setRepos)
      .catch((err) => setError(err.message ?? "Failed to load repositories"))
      .finally(() => setLoading(false));
  }, []);

  // SSE listener for real-time webhook alerts
  useEffect(() => {
    const es = new EventSource("/signals/stream", { withCredentials: true });

    es.onmessage = (e) => {
      try {
        const signal = JSON.parse(e.data) as SignalEvent;

        // Highlight the repo card
        setAlertedRepoIds((prev) => new Set([...prev, signal.repoId]));

        // Find the repo name for the toast
        setRepos((current) => {
          const repo = current.find((r) => r.id === signal.repoId);
          const repoName = repo ? `${repo.owner}/${repo.name}` : undefined;
          addToast(signal, repoName);
          return current; // no state change — just reading
        });

        // Clear the glow after 8 s
        setTimeout(() => {
          setAlertedRepoIds((prev) => {
            const next = new Set(prev);
            next.delete(signal.repoId);
            return next;
          });
        }, 8000);
      } catch {
        // ignore malformed messages
      }
    };

    es.onerror = () => {
      // SSE will auto-reconnect; no action needed
    };

    return () => es.close();
  }, [addToast]);

  const handleRepoAdded = useCallback((newRepo: Repo) => {
    setRepos((prev) => {
      if (prev.some((r) => r.id === newRepo.id)) return prev;
      return [newRepo, ...prev];
    });
  }, []);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      {/* Header */}
      <div
        style={{
          padding: "28px 32px 0",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "1.4rem",
              fontWeight: 700,
              color: "#f1f5f9",
              letterSpacing: "-0.02em",
              marginBottom: 4,
            }}
          >
            Repositories
          </h1>
          <p style={{ fontSize: "0.85rem", color: "#475569" }}>
            {repos.length > 0
              ? `${repos.length} connected repo${repos.length !== 1 ? "s" : ""}`
              : "Connect repos to start monitoring"}
          </p>
        </div>

        <button
          onClick={() => setModalOpen(true)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "9px 16px",
            background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
            border: "none",
            borderRadius: 9,
            color: "white",
            fontSize: "0.85rem",
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 4px 14px rgba(99,102,241,0.3)",
            transition: "transform 0.15s, box-shadow 0.15s",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 6px 18px rgba(99,102,241,0.4)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.transform = "translateY(0)";
            (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 14px rgba(99,102,241,0.3)";
          }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M7.75 2a.75.75 0 01.75.75V7h4.25a.75.75 0 010 1.5H8.5v4.25a.75.75 0 01-1.5 0V8.5H2.75a.75.75 0 010-1.5H7V2.75A.75.75 0 017.75 2z" />
          </svg>
          Add repository
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, padding: "24px 32px", overflowY: "auto" }}>
        {loading && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", paddingTop: 80 }}>
            <div
              style={{
                width: 28,
                height: 28,
                border: "3px solid rgba(99,102,241,0.2)",
                borderTopColor: "#6366f1",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
              }}
            />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {error && (
          <div
            style={{
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: 10,
              padding: "14px 18px",
              color: "#f87171",
              fontSize: "0.875rem",
            }}
          >
            {error}
          </div>
        )}

        {!loading && !error && repos.length === 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              paddingTop: 80,
              gap: 20,
            }}
          >
            {/* Empty state illustration */}
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: 20,
                background: "rgba(99,102,241,0.1)",
                border: "1px solid rgba(99,102,241,0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <svg width="32" height="32" viewBox="0 0 16 16" fill="#6366f1">
                <path d="M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z" />
              </svg>
            </div>
            <div style={{ textAlign: "center" }}>
              <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "#f1f5f9", marginBottom: 8 }}>
                No repositories yet
              </h3>
              <p style={{ fontSize: "0.875rem", color: "#475569", marginBottom: 20 }}>
                Connect your first GitHub repository to start monitoring issues and CI failures.
              </p>
              <button
                onClick={() => setModalOpen(true)}
                style={{
                  padding: "9px 20px",
                  background: "rgba(99,102,241,0.15)",
                  border: "1px solid rgba(99,102,241,0.35)",
                  borderRadius: 9,
                  color: "#818cf8",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                Add your first repository
              </button>
            </div>
          </div>
        )}

        {!loading && !error && repos.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 16,
            }}
          >
            {repos.map((repo) => (
              <RepoCard
                key={repo.id}
                repo={repo}
                onClick={() => navigate(`/repos/${repo.id}`)}
                isAlerted={alertedRepoIds.has(repo.id)}
              />
            ))}
          </div>
        )}
      </div>

      {modalOpen && (
        <AddRepoModal
          existingRepos={repos}
          onClose={() => setModalOpen(false)}
          onAdded={handleRepoAdded}
        />
      )}

      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}
