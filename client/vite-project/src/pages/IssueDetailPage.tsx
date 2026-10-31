import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { fixSignal, getSignalDetail, streamSignalProgress } from "../api/repos";
import type { FixAttempt, FixJobStatus, FixRun, JobEvent, SignalDetail } from "../types";
import { getSignalDisplay } from "../utils/signalDisplay";

// ── Run state helpers ────────────────────────────────────────────────────────

// Finished, or stopped after the fix validated but the PR could not be opened
function isRunFinished(run: FixRun): boolean {
  return (
    run.status === "pr_created" ||
    run.status === "failed" ||
    (run.status === "awaiting_approval" && !!run.error_message)
  );
}

const STEPS: { label: string; statuses: (FixJobStatus | "pr_failed")[] }[] = [
  { label: "Get latest code", statuses: ["queued", "reindexing"] },
  { label: "Find the problem", statuses: ["analyzing_signal", "localizing", "root_cause"] },
  { label: "Write a fix", statuses: ["generating"] },
  { label: "Test the fix", statuses: ["validating"] },
  { label: "Open pull request", statuses: ["awaiting_approval", "pr_created", "pr_failed"] },
];

function stepIndexOf(status: string): number {
  return STEPS.findIndex((s) => (s.statuses as string[]).includes(status));
}

type StepState = "done" | "active" | "failed" | "pending";

function stepStates(run: FixRun): StepState[] {
  if (run.status === "pr_created") return STEPS.map(() => "done");

  let current = stepIndexOf(run.status);
  let failed = run.status === "awaiting_approval" && !!run.error_message;
  if (run.status === "failed") {
    // The step it stopped in: the stage of the last event before the failure
    const last = [...run.events].reverse().find((e) => e.stage !== "failed");
    current = last ? Math.max(stepIndexOf(last.stage), 0) : 0;
    failed = true;
  }
  return STEPS.map((_, i) =>
    i < current ? "done" : i === current ? (failed ? "failed" : "active") : "pending"
  );
}

// Union two event lists by id, in recorded order
function mergeEvents(a: JobEvent[], b: JobEvent[]): JobEvent[] {
  const byId = new Map<string, JobEvent>();
  for (const e of [...a, ...b]) byId.set(e.id, e);
  return [...byId.values()].sort((x, y) => (x.cursor < y.cursor ? -1 : x.cursor > y.cursor ? 1 : 0));
}

// A refetch can be older than events already streamed in; keep both
function mergeDetail(prev: SignalDetail | null, next: SignalDetail): SignalDetail {
  if (!prev) return next;
  return {
    ...next,
    runs: next.runs.map((run) => {
      const old = prev.runs.find((r) => r.id === run.id);
      return old ? { ...run, events: mergeEvents(old.events, run.events) } : run;
    }),
  };
}

function latestCursor(detail: SignalDetail): string | undefined {
  let latest: string | undefined;
  for (const run of detail.runs) {
    for (const e of run.events) if (!latest || e.cursor > latest) latest = e.cursor;
  }
  return latest;
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDuration(from: string, to: string): string {
  const seconds = Math.max(0, Math.round((new Date(to).getTime() - new Date(from).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

const methodLabel: Record<string, string> = {
  stack_trace_direct: "named in the error trace",
  embedding: "similar to the report",
  mentioned_symbol: "mentioned in the report",
  keyword_search: "matched keywords from the report",
};

// ── Small presentational pieces ──────────────────────────────────────────────

const card: React.CSSProperties = {
  background: "#0a1020",
  border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: 12,
  padding: "18px 20px",
};

const sectionLabel: React.CSSProperties = {
  fontSize: "0.72rem",
  color: "#475569",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  marginBottom: 12,
};

const inlineCode: React.CSSProperties = {
  fontFamily: "monospace",
  fontSize: "0.92em",
  color: "#c4b5fd",
  background: "rgba(139,92,246,0.1)",
  padding: "1px 5px",
  borderRadius: 4,
  wordBreak: "break-all",
};

// Renders `code` spans and links inside an agent message
function RichText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`|https?:\/\/[^\s)]+)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("`") && part.endsWith("`") && part.length > 1) {
          return <code key={i} style={inlineCode}>{part.slice(1, -1)}</code>;
        }
        if (/^https?:\/\//.test(part)) {
          return (
            <a key={i} href={part} target="_blank" rel="noopener noreferrer" style={{ color: "#818cf8" }}>
              {part}
            </a>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

function Spinner({ size = 10 }: { size?: number }) {
  return (
    <span
      style={{
        width: size,
        height: size,
        border: "1.5px solid rgba(129,140,248,0.3)",
        borderTopColor: "#818cf8",
        borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
        display: "inline-block",
        flexShrink: 0,
      }}
    />
  );
}

function Collapsible({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 10 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "transparent",
          border: "none",
          color: "#818cf8",
          fontSize: "0.78rem",
          cursor: "pointer",
          padding: 0,
          display: "flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <svg
          width="11"
          height="11"
          viewBox="0 0 16 16"
          fill="currentColor"
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}
        >
          <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z" />
        </svg>
        {label}
      </button>
      {open && <div style={{ marginTop: 8 }}>{children}</div>}
    </div>
  );
}

const preBlock: React.CSSProperties = {
  fontFamily: "monospace",
  fontSize: "0.74rem",
  lineHeight: 1.5,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  margin: 0,
  maxHeight: 360,
  overflow: "auto",
  background: "rgba(0,0,0,0.3)",
  border: "1px solid rgba(255,255,255,0.05)",
  borderRadius: 8,
  padding: "10px 12px",
};

function DiffView({ diff }: { diff: string }) {
  return (
    <pre style={preBlock}>
      {diff.split("\n").map((line, i) => {
        const color =
          line.startsWith("+++") || line.startsWith("---")
            ? "#94a3b8"
            : line.startsWith("+")
            ? "#34d399"
            : line.startsWith("-")
            ? "#f87171"
            : line.startsWith("@@")
            ? "#818cf8"
            : "#64748b";
        return (
          <div key={i} style={{ color }}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

// ── Run sections ─────────────────────────────────────────────────────────────

function Stepper({ run }: { run: FixRun }) {
  const states = stepStates(run);
  const colors: Record<StepState, { dot: string; text: string }> = {
    done: { dot: "#34d399", text: "#94a3b8" },
    active: { dot: "#818cf8", text: "#f1f5f9" },
    failed: { dot: "#f87171", text: "#f87171" },
    pending: { dot: "#1e293b", text: "#475569" },
  };
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {STEPS.map((step, i) => {
        const state = states[i] ?? "pending";
        const c = colors[state];
        return (
          <div
            key={step.label}
            style={{
              flex: "1 1 140px",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div
              style={{
                height: 3,
                borderRadius: 999,
                background: state === "pending" ? "rgba(255,255,255,0.06)" : c.dot,
                opacity: state === "done" ? 0.6 : 1,
              }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.78rem", color: c.text }}>
              {state === "active" ? (
                <Spinner />
              ) : state === "done" ? (
                <svg width="11" height="11" viewBox="0 0 16 16" fill="#34d399">
                  <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
                </svg>
              ) : state === "failed" ? (
                <svg width="11" height="11" viewBox="0 0 16 16" fill="#f87171">
                  <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
                </svg>
              ) : (
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#1e293b", flexShrink: 0 }} />
              )}
              {step.label}
              {i === 2 && run.attempt_count > 1 && state !== "pending" && (
                <span style={{ color: "#475569" }}>· attempt {run.attempt_count}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ActivityFeed({ run, live }: { run: FixRun; live: boolean }) {
  const endRef = useRef<HTMLDivElement>(null);
  const count = run.events.length;

  // Follow new activity while the run is live
  useEffect(() => {
    if (live) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [count, live]);

  if (count === 0) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem", color: "#64748b" }}>
        {live && <Spinner />}
        {live ? "Waiting for the AutoFix agent to pick this up…" : "No activity was recorded for this run."}
      </div>
    );
  }

  return (
    <div style={{ maxHeight: 420, overflowY: "auto", paddingRight: 4 }}>
      {run.events.map((event, i) => {
        const isLast = i === count - 1;
        const isError = event.stage === "failed" || event.stage === "pr_failed";
        const isSuccess = event.stage === "pr_created";
        const dotColor = isError ? "#f87171" : isSuccess ? "#34d399" : isLast && live ? "#818cf8" : "#334155";
        return (
          <div key={event.id} style={{ display: "flex", gap: 12, position: "relative", paddingBottom: isLast ? 0 : 12 }}>
            {/* Rail */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 10, flexShrink: 0 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: dotColor,
                  marginTop: 6,
                  boxShadow: isLast && live ? "0 0 0 4px rgba(129,140,248,0.15)" : "none",
                }}
              />
              {!isLast && <span style={{ flex: 1, width: 1, background: "rgba(255,255,255,0.06)", marginTop: 4 }} />}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: "0.85rem",
                  lineHeight: 1.5,
                  color: isError ? "#fca5a5" : isSuccess ? "#6ee7b7" : isLast && live ? "#f1f5f9" : "#94a3b8",
                }}
              >
                <RichText text={event.message} />
              </div>
              <div style={{ fontSize: "0.7rem", color: "#334155", marginTop: 2 }}>{formatTime(event.created_at)}</div>
            </div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}

function OutcomeBanner({ run }: { run: FixRun }) {
  const tried = run.attempts.length;
  const triedText = tried === 1 ? "1 attempt" : `${tried} attempts`;

  let tone: "success" | "warning" | "error";
  let title: string;
  let body: React.ReactNode;

  if (run.status === "pr_created") {
    tone = "success";
    title = "Fixed — a pull request is ready for review";
    body = (
      <>
        AutoFix found a change that passed all checks after {triedText}.{" "}
        {run.pull_request && (
          <a href={run.pull_request.pr_url} target="_blank" rel="noopener noreferrer" style={{ color: "#34d399", fontWeight: 600 }}>
            Review pull request #{run.pull_request.pr_number} →
          </a>
        )}
      </>
    );
  } else if (run.status === "awaiting_approval") {
    tone = "warning";
    title = "Fix found, but the pull request couldn't be opened";
    body = "The change passed all checks, but GitHub rejected the pull request. Logging in again to refresh GitHub permissions usually fixes this; then retry.";
  } else {
    tone = "error";
    title = "AutoFix couldn't fix this automatically";
    body =
      tried > 0
        ? `It made ${triedText}, but none passed all checks. Here's everything it tried, so you can pick up from there.`
        : "It stopped before it could propose a change. The activity above shows how far it got.";
  }

  const palette = {
    success: { bg: "rgba(16,185,129,0.08)", border: "rgba(16,185,129,0.3)", color: "#34d399" },
    warning: { bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.3)", color: "#fbbf24" },
    error: { bg: "rgba(239,68,68,0.08)", border: "rgba(239,68,68,0.3)", color: "#f87171" },
  }[tone];

  return (
    <div style={{ background: palette.bg, border: `1px solid ${palette.border}`, borderRadius: 12, padding: "14px 18px" }}>
      <div style={{ fontSize: "0.95rem", fontWeight: 600, color: palette.color, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: "0.85rem", color: "#cbd5e1", lineHeight: 1.55 }}>{body}</div>
      <div style={{ fontSize: "0.72rem", color: "#64748b", marginTop: 8 }}>
        Took {formatDuration(run.created_at, run.updated_at)}
      </div>
    </div>
  );
}

function AttemptCard({ attempt }: { attempt: FixAttempt }) {
  const pending = attempt.validation_passed === null;
  const passed = attempt.validation_passed === true;
  const noChange = !attempt.diff_content.trim();
  const badge = pending
    ? { label: "Testing…", color: "#818cf8", bg: "rgba(99,102,241,0.12)" }
    : passed
    ? { label: "Passed", color: "#34d399", bg: "rgba(16,185,129,0.12)" }
    : noChange
    ? { label: "No change proposed", color: "#fbbf24", bg: "rgba(245,158,11,0.12)" }
    : { label: "Didn't pass", color: "#f87171", bg: "rgba(239,68,68,0.12)" };

  return (
    <div style={{ border: "1px solid rgba(255,255,255,0.06)", borderRadius: 10, padding: "14px 16px", background: "rgba(0,0,0,0.15)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#f1f5f9" }}>Attempt {attempt.attempt_number}</span>
        <span
          style={{
            fontSize: "0.67rem",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            padding: "2px 7px",
            borderRadius: 999,
            background: badge.bg,
            color: badge.color,
            display: "flex",
            alignItems: "center",
            gap: 5,
          }}
        >
          {pending && <Spinner size={8} />}
          {badge.label}
        </span>
      </div>

      {attempt.explanation && (
        <div style={{ fontSize: "0.84rem", color: "#cbd5e1", lineHeight: 1.55, marginBottom: 6 }}>
          <span style={{ color: "#64748b" }}>What the AI tried: </span>
          <RichText text={attempt.explanation} />
        </div>
      )}
      {attempt.outcome && !passed && (
        <div style={{ fontSize: "0.84rem", color: "#fca5a5", lineHeight: 1.55 }}>
          <span style={{ color: "#64748b" }}>Result: </span>
          {attempt.outcome}
        </div>
      )}

      {!noChange && (
        <Collapsible label="View the proposed change">
          <DiffView diff={attempt.diff_content} />
          {attempt.diff_truncated && (
            <div style={{ fontSize: "0.72rem", color: "#64748b", marginTop: 4 }}>Change truncated for display.</div>
          )}
        </Collapsible>
      )}
      {attempt.log_excerpt && !passed && (
        <Collapsible label="Technical details (test output)">
          <pre style={{ ...preBlock, color: "#94a3b8" }}>{attempt.log_excerpt}</pre>
        </Collapsible>
      )}
    </div>
  );
}

function WhatWasTried({ run }: { run: FixRun }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "#cbd5e1", marginBottom: 8 }}>Where it looked</div>
        {run.candidates.length === 0 ? (
          <div style={{ fontSize: "0.84rem", color: "#64748b" }}>
            No specific location stood out from the report, so the AI explored the code on its own.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {run.candidates.slice(0, 5).map((c) => (
              <div key={`${c.rank}-${c.file_path}`} style={{ fontSize: "0.82rem", color: "#94a3b8", display: "flex", gap: 8, flexWrap: "wrap" }}>
                <code style={inlineCode}>{c.file_path}</code>
                <span>lines {c.start_line}–{c.end_line}</span>
                <span style={{ color: "#475569" }}>· {methodLabel[c.method] ?? "found by search"}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {run.attempts.length > 0 && (
        <div>
          <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "#cbd5e1", marginBottom: 8 }}>Fix attempts</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {run.attempts.map((a) => (
              <AttemptCard key={a.attempt_number} attempt={a} />
            ))}
          </div>
        </div>
      )}

      {run.error_message && (
        <Collapsible label="Technical details (error)">
          <pre style={{ ...preBlock, color: "#94a3b8" }}>{run.error_message}</pre>
        </Collapsible>
      )}
    </div>
  );
}

function RunView({ run }: { run: FixRun }) {
  const finished = isRunFinished(run);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={card}>
        <Stepper run={run} />
      </div>

      {finished && <OutcomeBanner run={run} />}

      <div style={card}>
        <div style={{ ...sectionLabel, display: "flex", alignItems: "center", gap: 8 }}>
          {finished ? "What happened" : "Live activity"}
          {!finished && (
            <span style={{ display: "flex", alignItems: "center", gap: 5, color: "#818cf8", textTransform: "none", letterSpacing: 0 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#818cf8", animation: "pulse-glow 1.5s ease-in-out infinite" }} />
              live
            </span>
          )}
        </div>
        <ActivityFeed run={run} live={!finished} />
      </div>

      {(finished || run.attempts.length > 0 || run.candidates.length > 0) && (
        <div style={card}>
          <div style={sectionLabel}>{finished ? "What was tried" : "Progress so far"}</div>
          <WhatWasTried run={run} />
        </div>
      )}
    </div>
  );
}

function PreviousRun({ run }: { run: FixRun }) {
  const [open, setOpen] = useState(false);
  const label =
    run.status === "pr_created" ? "Fixed" : run.status === "failed" ? "Not fixed" : "Stopped";
  return (
    <div style={{ ...card, padding: 0 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: "100%",
          background: "transparent",
          border: "none",
          padding: "14px 18px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          cursor: "pointer",
          color: "#94a3b8",
          fontSize: "0.84rem",
          textAlign: "left",
        }}
      >
        <svg
          width="11"
          height="11"
          viewBox="0 0 16 16"
          fill="currentColor"
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}
        >
          <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z" />
        </svg>
        <span style={{ color: "#cbd5e1" }}>Run from {formatDateTime(run.created_at)}</span>
        <span style={{ color: run.status === "pr_created" ? "#34d399" : "#f87171" }}>· {label}</span>
        <span style={{ color: "#475569" }}>
          · {run.attempts.length} attempt{run.attempts.length === 1 ? "" : "s"}
        </span>
      </button>
      {open && (
        <div style={{ padding: "0 18px 18px" }}>
          <RunView run={run} />
        </div>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function IssueDetailPage() {
  const { id, signalId } = useParams<{ id: string; signalId: string }>();
  const [detail, setDetail] = useState<SignalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fixing, setFixing] = useState(false);
  const [fixError, setFixError] = useState<string | null>(null);
  // Runs currently on the page, for routing streamed events outside React state
  const runIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    runIdsRef.current = new Set(detail?.runs.map((r) => r.id) ?? []);
  }, [detail]);

  const refresh = useCallback(async () => {
    if (!id || !signalId) return;
    const next = await getSignalDetail(id, signalId);
    setDetail((prev) => mergeDetail(prev, next));
  }, [id, signalId]);

  // Initial load, then live updates over SSE
  useEffect(() => {
    if (!id || !signalId) return;
    let cancelled = false;
    let es: EventSource | null = null;

    getSignalDetail(id, signalId)
      .then((data) => {
        if (cancelled) return;
        runIdsRef.current = new Set(data.runs.map((r) => r.id));
        setDetail(data);
        es = streamSignalProgress(id, signalId, latestCursor(data));

        es.addEventListener("progress", (e) => {
          let event: JobEvent;
          try {
            event = JSON.parse((e as MessageEvent).data);
          } catch {
            return;
          }
          // A run this page hasn't loaded yet (e.g. started from another tab)
          if (!runIdsRef.current.has(event.job_id)) {
            refresh().catch(() => {});
            return;
          }
          setDetail((prev) =>
            prev && {
              ...prev,
              runs: prev.runs.map((r) =>
                r.id === event.job_id ? { ...r, events: mergeEvents(r.events, [event]) } : r
              ),
            }
          );
        });

        // Status changed: refetch for attempts, outcome and PR
        es.addEventListener("run", () => {
          refresh().catch(() => {});
        });
      })
      .catch((err) => setError(err.message ?? "Failed to load issue"))
      .finally(() => setLoading(false));

    return () => {
      cancelled = true;
      es?.close();
    };
  }, [id, signalId, refresh]);

  const handleFix = async () => {
    if (!id || !signalId || fixing) return;
    setFixing(true);
    setFixError(null);
    try {
      await fixSignal(id, signalId);
      await refresh();
    } catch (err: unknown) {
      setFixError(err instanceof Error ? err.message : "Failed to queue fix");
    } finally {
      setFixing(false);
    }
  };

  const signal = detail?.signal;
  const display = signal ? getSignalDisplay(signal) : null;
  const [latestRun, ...previousRuns] = detail?.runs ?? [];
  const canFix = !latestRun || latestRun.status === "failed";

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      {/* Header */}
      <div style={{ padding: "24px 32px", borderBottom: "1px solid rgba(255,255,255,0.05)", flexShrink: 0 }}>
        <Link
          to={`/repos/${id}`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            color: "#475569",
            fontSize: "0.8rem",
            textDecoration: "none",
            marginBottom: 16,
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.color = "#94a3b8")}
          onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.color = "#475569")}
        >
          <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
            <path d="M9.78 12.78a.75.75 0 01-1.06 0L4.47 8.53a.75.75 0 010-1.06l4.25-4.25a.75.75 0 011.06 1.06L6.06 8l3.72 3.72a.75.75 0 010 1.06z" />
          </svg>
          Back to repository
        </Link>

        {loading ? (
          <div style={{ height: 32, width: 260, borderRadius: 8, background: "rgba(255,255,255,0.04)" }} />
        ) : signal && display ? (
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span
                  style={{
                    fontSize: "0.68rem",
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: display.isIssue ? "rgba(99,102,241,0.12)" : "rgba(239,68,68,0.1)",
                    color: display.isIssue ? "#a78bfa" : "#f87171",
                  }}
                >
                  {display.isIssue ? "Issue" : "CI failure"}
                </span>
                <h1 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#f1f5f9", letterSpacing: "-0.01em" }}>
                  {display.title}
                </h1>
              </div>
              <div style={{ fontSize: "0.8rem", color: "#64748b", marginTop: 6, display: "flex", gap: 10, flexWrap: "wrap" }}>
                <span>{display.subtitle}</span>
                {display.externalUrl && (
                  <a href={display.externalUrl} target="_blank" rel="noopener noreferrer" style={{ color: "#818cf8", textDecoration: "none" }}>
                    View on GitHub ↗
                  </a>
                )}
              </div>
            </div>

            {canFix && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                <button
                  onClick={handleFix}
                  disabled={fixing}
                  style={{
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    padding: "8px 16px",
                    borderRadius: 9,
                    background: fixing ? "rgba(99,102,241,0.15)" : "#4f46e5",
                    color: "#fff",
                    border: "1px solid rgba(99,102,241,0.5)",
                    cursor: fixing ? "default" : "pointer",
                  }}
                >
                  {fixing ? "Queuing…" : latestRun ? "Retry fix" : "Fix with AutoFix"}
                </button>
                {fixError && <span style={{ fontSize: "0.72rem", color: "#f87171" }}>{fixError}</span>}
              </div>
            )}
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
      {!loading && signal && display && (
        <div style={{ flex: 1, padding: "24px 32px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 16, maxWidth: 1000 }}>
          {/* Report */}
          <div style={card}>
            <div style={sectionLabel}>{display.isIssue ? "Reported problem" : "Failed run"}</div>
            {display.isIssue ? (
              <pre style={{ ...preBlock, background: "transparent", border: "none", padding: 0, maxHeight: 200, color: "#94a3b8", fontFamily: "inherit", fontSize: "0.85rem" }}>
                {display.issueData?.body || "No description provided."}
              </pre>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "6px 16px", fontSize: "0.8rem" }}>
                {[
                  ["Branch", display.ciData?.branch],
                  ["Commit", display.ciData?.head_sha?.slice(0, 7)],
                  ["Triggered by", display.ciData?.event],
                  ["Run #", String(display.ciData?.run_number ?? "")],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span style={{ color: "#475569", marginRight: 4 }}>{label}:</span>
                    <span style={{ color: "#94a3b8", fontFamily: "monospace" }}>{value}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {latestRun ? (
            <RunView key={latestRun.id} run={latestRun} />
          ) : (
            <div style={{ ...card, textAlign: "center", padding: "40px 20px" }}>
              <p style={{ fontSize: "0.9rem", color: "#94a3b8" }}>AutoFix hasn't worked on this yet.</p>
              <p style={{ fontSize: "0.8rem", color: "#475569", marginTop: 4 }}>
                Click “Fix with AutoFix” and you'll be able to follow every step here as it happens.
              </p>
            </div>
          )}

          {previousRuns.length > 0 && (
            <div>
              <div style={{ ...sectionLabel, marginTop: 8 }}>Earlier runs</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {previousRuns.map((run) => (
                  <PreviousRun key={run.id} run={run} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
