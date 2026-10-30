import { useState } from "react";
import type { Signal, IssueSignalData, CiFailureSignalData, FixJobStatus } from "../types";

interface Props {
  signal: Signal;
  onFix?: (signal: Signal) => Promise<void>;
}

const jobStageLabel: Record<FixJobStatus, string> = {
  queued: "Queued",
  reindexing: "Indexing",
  analyzing_signal: "Analyzing",
  localizing: "Localizing",
  root_cause: "Root cause",
  generating: "Generating fix",
  validating: "Validating",
  awaiting_approval: "Opening PR",
  pr_created: "PR opened",
  failed: "Failed",
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const statusConfig = {
  open: { label: "Open", color: "#fbbf24", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.3)" },
  in_progress: { label: "In Progress", color: "#818cf8", bg: "rgba(99,102,241,0.12)", border: "rgba(99,102,241,0.3)" },
  resolved: { label: "Resolved", color: "#34d399", bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.3)" },
  failed: { label: "Failed", color: "#f87171", bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.3)" },
  ignored: { label: "Ignored", color: "#64748b", bg: "rgba(100,116,139,0.12)", border: "rgba(100,116,139,0.25)" },
};

export default function SignalCard({ signal, onFix }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fixError, setFixError] = useState<string | null>(null);

  const jobStatus = signal.job_status;
  const canFix = !jobStatus || jobStatus === "failed";
  // awaiting_approval + error_message means the patch validated but the PR push failed
  const prFailed = jobStatus === "awaiting_approval" && !!signal.job_error;

  const handleFix = async () => {
    if (!onFix || fixing) return;
    setFixing(true);
    setFixError(null);
    try {
      await onFix(signal);
    } catch (err: unknown) {
      setFixError(err instanceof Error ? err.message : "Failed to queue fix");
    } finally {
      setFixing(false);
    }
  };
  const isIssue = signal.type === "github_issue";
  const status = statusConfig[signal.status] ?? statusConfig.open;

  const rawParsed = typeof signal.parsed_data === "string" ? (() => {
    try { return JSON.parse(signal.parsed_data); } catch { return {}; }
  })() : (signal.parsed_data || {});

  const issueData = isIssue ? (rawParsed as IssueSignalData) : null;
  const ciData = !isIssue ? (rawParsed as CiFailureSignalData) : null;

  const title = isIssue
    ? issueData?.title ?? `Issue #${signal.source_ref}`
    : ciData?.workflow_name ?? `Workflow run ${signal.source_ref}`;

  const subtitle = isIssue
    ? `#${issueData?.number} opened by ${issueData?.author ?? "unknown"}`
    : `${ciData?.branch} · run #${ciData?.run_number} · triggered by ${ciData?.actor ?? "unknown"}`;

  const externalUrl = isIssue ? issueData?.url : ciData?.html_url;

  return (
    <div
      style={{
        background: "#0a1020",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 10,
        overflow: "hidden",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={(e) => ((e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.12)")}
      onMouseLeave={(e) => ((e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.06)")}
    >
      {/* Main row */}
      <div style={{ padding: "14px 16px", display: "flex", alignItems: "flex-start", gap: 12 }}>
        {/* Type icon */}
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 8,
            background: isIssue ? "rgba(99,102,241,0.12)" : "rgba(239,68,68,0.1)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {isIssue ? (
            <svg width="15" height="15" viewBox="0 0 16 16" fill="#a78bfa">
              <path d="M8 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" />
              <path fillRule="evenodd" d="M8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z" />
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 16 16" fill="#f87171">
              <path fillRule="evenodd" d="M8.22 1.754a.25.25 0 00-.44 0L1.698 13.132a.25.25 0 00.22.368h12.164a.25.25 0 00.22-.368L8.22 1.754zm-1.763-.707c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0114.082 15H1.918a1.75 1.75 0 01-1.543-2.575L6.457 1.047zM9 11a1 1 0 11-2 0 1 1 0 012 0zm-.25-5.25a.75.75 0 00-1.5 0v2.5a.75.75 0 001.5 0v-2.5z" />
            </svg>
          )}
        </div>

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 3 }}>
            <span style={{ fontSize: "0.875rem", fontWeight: 500, color: "#f1f5f9" }}>
              {title}
            </span>
            {/* Status badge */}
            <span
              style={{
                fontSize: "0.67rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                padding: "2px 7px",
                borderRadius: 999,
                background: status.bg,
                color: status.color,
                border: `1px solid ${status.border}`,
              }}
            >
              {status.label}
            </span>
          </div>
          <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
            {subtitle}
          </div>
          {(fixError || (jobStatus === "failed" && signal.job_error) || prFailed) && (
            <div
              style={{ fontSize: "0.72rem", color: "#f87171", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              title={fixError ?? signal.job_error ?? undefined}
            >
              {fixError ?? signal.job_error}
            </div>
          )}
          {/* Labels for issues */}
          {isIssue && issueData?.labels && issueData.labels.length > 0 && (
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 6 }}>
              {issueData.labels.map((label) => (
                <span
                  key={label}
                  style={{
                    fontSize: "0.68rem",
                    padding: "1px 6px",
                    borderRadius: 999,
                    background: "rgba(99,102,241,0.1)",
                    color: "#818cf8",
                    border: "1px solid rgba(99,102,241,0.2)",
                  }}
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Right side */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {/* Fix job: button / live stage / PR link */}
          {jobStatus === "pr_created" && signal.pr_url ? (
            <a
              href={signal.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                padding: "4px 10px",
                borderRadius: 7,
                background: "rgba(16,185,129,0.1)",
                color: "#34d399",
                border: "1px solid rgba(16,185,129,0.3)",
                textDecoration: "none",
                whiteSpace: "nowrap",
              }}
              title="View pull request on GitHub"
            >
              PR #{signal.pr_number}
            </a>
          ) : canFix && onFix ? (
            <button
              onClick={handleFix}
              disabled={fixing}
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                padding: "4px 12px",
                borderRadius: 7,
                background: fixing ? "rgba(99,102,241,0.15)" : "#4f46e5",
                color: "#fff",
                border: "1px solid rgba(99,102,241,0.5)",
                cursor: fixing ? "default" : "pointer",
                whiteSpace: "nowrap",
                transition: "background 0.15s",
              }}
              title="Queue an AutoFix job for this signal"
            >
              {fixing ? "Queuing…" : jobStatus === "failed" ? "Retry fix" : "Fix"}
            </button>
          ) : jobStatus ? (
            <span
              style={{
                fontSize: "0.72rem",
                fontWeight: 600,
                padding: "4px 10px",
                borderRadius: 7,
                background: prFailed ? "rgba(239,68,68,0.1)" : "rgba(99,102,241,0.1)",
                color: prFailed ? "#f87171" : "#818cf8",
                border: `1px solid ${prFailed ? "rgba(239,68,68,0.3)" : "rgba(99,102,241,0.3)"}`,
                display: "flex",
                alignItems: "center",
                gap: 6,
                whiteSpace: "nowrap",
              }}
              title={signal.job_error ?? undefined}
            >
              {!prFailed && (
                <span
                  style={{
                    width: 9,
                    height: 9,
                    border: "1.5px solid rgba(129,140,248,0.3)",
                    borderTopColor: "#818cf8",
                    borderRadius: "50%",
                    animation: "spin 0.8s linear infinite",
                  }}
                />
              )}
              {prFailed ? "PR failed" : jobStageLabel[jobStatus]}
            </span>
          ) : null}

          <span style={{ fontSize: "0.72rem", color: "#475569", whiteSpace: "nowrap" }}>
            {timeAgo(signal.created_at)}
          </span>

          {/* External link */}
          {externalUrl && (
            <a
              href={externalUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "#475569", display: "flex", alignItems: "center" }}
              onClick={(e) => e.stopPropagation()}
              title="View on GitHub"
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                <path fillRule="evenodd" d="M10.604 1h4.146a.25.25 0 01.25.25v4.146a.25.25 0 01-.427.177L13.03 4.03 9.28 7.78a.75.75 0 01-1.06-1.06l3.75-3.75-1.543-1.543A.25.25 0 0110.604 1zM3.75 2A1.75 1.75 0 002 3.75v8.5c0 .966.784 1.75 1.75 1.75h8.5A1.75 1.75 0 0014 12.25v-3.5a.75.75 0 00-1.5 0v3.5a.25.25 0 01-.25.25h-8.5a.25.25 0 01-.25-.25v-8.5a.25.25 0 01.25-.25h3.5a.75.75 0 000-1.5h-3.5z" />
              </svg>
            </a>
          )}

          {/* Expand toggle */}
          <button
            onClick={() => setExpanded((v) => !v)}
            style={{
              background: "transparent",
              border: "none",
              color: "#475569",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              padding: 0,
              transition: "color 0.15s",
            }}
            title={expanded ? "Collapse" : "Expand details"}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="currentColor"
              style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}
            >
              <path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Expanded raw content */}
      {expanded && (
        <div
          style={{
            borderTop: "1px solid rgba(255,255,255,0.05)",
            padding: "12px 16px",
            background: "rgba(0,0,0,0.2)",
          }}
        >
          {isIssue && issueData?.body && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: "0.72rem", color: "#475569", marginBottom: 4, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em" }}>Issue body</div>
              <pre
                style={{
                  fontFamily: "monospace",
                  fontSize: "0.75rem",
                  color: "#94a3b8",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  margin: 0,
                  maxHeight: 200,
                  overflowY: "auto",
                }}
              >
                {issueData.body}
              </pre>
            </div>
          )}
          {!isIssue && ciData && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px" }}>
              {[
                ["Branch", ciData.branch],
                ["Commit", ciData.head_sha?.slice(0, 7)],
                ["Triggered by", ciData.event],
                ["Run #", String(ciData.run_number)],
              ].map(([label, value]) => (
                <div key={label}>
                  <span style={{ fontSize: "0.7rem", color: "#475569", marginRight: 4 }}>{label}:</span>
                  <span style={{ fontSize: "0.75rem", color: "#94a3b8", fontFamily: "monospace" }}>{value}</span>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: "0.72rem", color: "#475569", marginBottom: 4, fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.04em" }}>Raw content</div>
            <pre
              style={{
                fontFamily: "monospace",
                fontSize: "0.72rem",
                color: "#64748b",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
                maxHeight: 120,
                overflowY: "auto",
              }}
            >
              {signal.raw_content}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
