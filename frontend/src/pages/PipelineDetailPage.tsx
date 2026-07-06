import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiErrorMessage } from "../lib/api";
import { pipelines as pipelinesApi } from "../lib/resources";
import type { Pipeline, PipelineRun, RunStatus } from "../lib/types";
import { StatusBadge } from "../components/StatusBadge";

const TERMINAL_STATUSES: RunStatus[] = ["SUCCEEDED", "FAILED"];
const POLL_INTERVAL_MS = 1500;

export function PipelineDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const pollingRunId = useRef<string | null>(null);

  const loadPipeline = useCallback(async () => {
    if (!id) return;
    const response = await pipelinesApi.get(id);
    setPipeline(response.data);
  }, [id]);

  const loadRuns = useCallback(async () => {
    if (!id) return;
    const response = await pipelinesApi.runs(id);
    setRuns(response.data.results);
  }, [id]);

  useEffect(() => {
    void loadPipeline();
    void loadRuns();
  }, [loadPipeline, loadRuns]);

  // Polls the just-triggered run until it reaches a terminal status, so "Run status updates"
  // (the v0.8 acceptance criterion) works without the user manually refreshing the page.
  useEffect(() => {
    if (!pollingRunId.current) return;
    const interval = setInterval(async () => {
      const runId = pollingRunId.current;
      if (!runId) return;
      const response = await pipelinesApi.getRun(runId);
      setRuns((prev) => prev.map((r) => (r.id === runId ? response.data : r)));
      if (TERMINAL_STATUSES.includes(response.data.status)) {
        pollingRunId.current = null;
        clearInterval(interval);
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [runs.length]);

  if (!id) return null;

  const runAction = async (action: () => Promise<unknown>) => {
    setActionBusy(true);
    setError(null);
    try {
      await action();
      await loadPipeline();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setActionBusy(false);
    }
  };

  const handleRun = () =>
    runAction(async () => {
      const response = await pipelinesApi.run(id);
      setRuns((prev) => [response.data, ...prev]);
      if (!TERMINAL_STATUSES.includes(response.data.status)) {
        pollingRunId.current = response.data.id;
      }
    });

  const handleClone = () =>
    runAction(async () => {
      const response = await pipelinesApi.clone(id);
      navigate(`/pipelines/${response.data.id}`);
    });

  if (!pipeline) {
    return <div className="page-loading">Loading…</div>;
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>{pipeline.name}</h1>
        <div className="button-row">
          <button type="button" onClick={handleRun} disabled={actionBusy}>
            Run now
          </button>
          {pipeline.is_active ? (
            <button
              type="button"
              className="ghost"
              onClick={() => runAction(() => pipelinesApi.pause(id))}
              disabled={actionBusy}
            >
              Pause
            </button>
          ) : (
            <button
              type="button"
              className="ghost"
              onClick={() => runAction(() => pipelinesApi.resume(id))}
              disabled={actionBusy}
            >
              Resume
            </button>
          )}
          <button type="button" className="ghost" onClick={handleClone} disabled={actionBusy}>
            Clone
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        <h3>Configuration</h3>
        <dl className="definition-list">
          <dt>Schedule</dt>
          <dd>{pipeline.schedule || "manual only"}</dd>
          <dt>Target</dt>
          <dd>{pipeline.config.target}</dd>
          <dt>Status</dt>
          <dd>{pipeline.is_active ? "Active" : "Paused"}</dd>
        </dl>
        <details>
          <summary>Raw config</summary>
          <pre className="code-block">{JSON.stringify(pipeline.config, null, 2)}</pre>
        </details>
      </div>

      <div className="card">
        <h3>Run history</h3>
        {runs.length === 0 ? (
          <p className="muted">No runs yet — click “Run now” to trigger one.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Rows loaded</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td>{run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</td>
                  <td>{run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</td>
                  <td>{typeof run.metrics.rows_loaded === "number" ? run.metrics.rows_loaded : "—"}</td>
                  <td className="error-cell">{run.error || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
