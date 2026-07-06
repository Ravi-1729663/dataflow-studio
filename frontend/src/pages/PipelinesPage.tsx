import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiErrorMessage } from "../lib/api";
import { pipelines as pipelinesApi } from "../lib/resources";
import type { Pipeline } from "../lib/types";
import { WorkspaceGate } from "../components/WorkspaceGate";

function PipelinesForWorkspace({ workspaceId }: { workspaceId: string }) {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await pipelinesApi.list(workspaceId);
      setPipelines(response.data.results);
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Pipelines</h1>
        <Link className="button-link" to="/pipelines/new">
          + New pipeline
        </Link>
      </div>
      <div className="card">
        {error && <div className="alert alert-error">{error}</div>}
        {loading ? (
          <p>Loading…</p>
        ) : pipelines.length === 0 ? (
          <p className="muted">No pipelines in this workspace yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Schedule</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pipelines.map((pipeline) => (
                <tr key={pipeline.id}>
                  <td>
                    <Link to={`/pipelines/${pipeline.id}`}>{pipeline.name}</Link>
                  </td>
                  <td>{pipeline.schedule || <span className="muted">manual only</span>}</td>
                  <td>{pipeline.is_active ? "Active" : "Paused"}</td>
                  <td>
                    <Link className="ghost" to={`/pipelines/${pipeline.id}`}>
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function PipelinesPage() {
  return (
    <WorkspaceGate>{(workspace) => <PipelinesForWorkspace workspaceId={workspace.id} />}</WorkspaceGate>
  );
}
