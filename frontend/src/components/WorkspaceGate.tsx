import type { ReactNode } from "react";
import { useWorkspace } from "../context/useWorkspace";
import type { Workspace } from "../lib/types";

/** Renders `children(workspace)` once a workspace is selected; otherwise a prompt to create
 * one. Every workspace-scoped page (data sources, pipelines, ...) needs this — there is no
 * useful "no workspace" state for them. */
export function WorkspaceGate({ children }: { children: (workspace: Workspace) => ReactNode }) {
  const { current, loading, workspaces } = useWorkspace();

  if (loading) {
    return <div className="page-loading">Loading workspaces…</div>;
  }
  if (!current) {
    return (
      <div className="empty-state">
        <h2>No workspace yet</h2>
        <p>
          {workspaces.length === 0
            ? "Create a workspace using the “+ New” control in the header to get started."
            : "Select a workspace from the header."}
        </p>
      </div>
    );
  }
  return <>{children(current)}</>;
}
