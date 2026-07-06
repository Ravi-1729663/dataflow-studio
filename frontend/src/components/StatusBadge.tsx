import type { RunStatus } from "../lib/types";

const LABELS: Record<RunStatus, string> = {
  PENDING: "Pending",
  RUNNING: "Running",
  RETRYING: "Retrying",
  SUCCEEDED: "Succeeded",
  FAILED: "Failed",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return <span className={`badge badge-${status.toLowerCase()}`}>{LABELS[status]}</span>;
}
