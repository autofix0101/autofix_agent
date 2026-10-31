import type { CiFailureSignalData, IssueSignalData, Signal } from "../types";

type SignalLike = Pick<Signal, "type" | "source_ref" | "parsed_data">;

// parsed_data can arrive as a JSON string depending on the driver
function parseData(signal: SignalLike): Record<string, unknown> {
  if (typeof signal.parsed_data === "string") {
    try {
      return JSON.parse(signal.parsed_data);
    } catch {
      return {};
    }
  }
  return (signal.parsed_data as unknown as Record<string, unknown>) || {};
}

/** Title, subtitle and GitHub link for an issue or CI failure signal. */
export function getSignalDisplay(signal: SignalLike) {
  const isIssue = signal.type === "github_issue";
  const raw = parseData(signal);
  const issueData = isIssue ? (raw as unknown as IssueSignalData) : null;
  const ciData = !isIssue ? (raw as unknown as CiFailureSignalData) : null;

  const title = isIssue
    ? issueData?.title ?? `Issue #${signal.source_ref}`
    : ciData?.workflow_name ?? `Workflow run ${signal.source_ref}`;

  const subtitle = isIssue
    ? `#${issueData?.number} opened by ${issueData?.author ?? "unknown"}`
    : `${ciData?.branch} · run #${ciData?.run_number} · triggered by ${ciData?.actor ?? "unknown"}`;

  const externalUrl = isIssue ? issueData?.url : ciData?.html_url;

  return { isIssue, issueData, ciData, title, subtitle, externalUrl };
}
