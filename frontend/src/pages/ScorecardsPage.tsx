import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiErrorMessage } from "../lib/api";
import { pipelines as pipelinesApi, validation } from "../lib/resources";
import type { Pipeline, QualityScorecard } from "../lib/types";
import { WorkspaceGate } from "../components/WorkspaceGate";

function ScorecardsForWorkspace({ workspaceId }: { workspaceId: string }) {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [selected, setSelected] = useState("");
  const [scorecards, setScorecards] = useState<QualityScorecard[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    pipelinesApi
      .list(workspaceId)
      .then((response) => {
        setPipelines(response.data.results);
        setSelected((prev) => prev || (response.data.results[0]?.id ?? ""));
      })
      .catch((err: unknown) => setError(apiErrorMessage(err)));
  }, [workspaceId]);

  useEffect(() => {
    if (!selected) return;
    validation
      .scorecards(selected)
      .then((response) => setScorecards(response.data.results))
      .catch((err: unknown) => setError(apiErrorMessage(err)));
  }, [selected]);

  const chartData = scorecards.map((s) => ({
    date: new Date(s.created_at).toLocaleDateString(),
    score: s.overall_score,
  }));

  return (
    <div className="page">
      <h1>Quality Scorecards</h1>
      <div className="card">
        <label>
          Pipeline
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {pipelines.length === 0 && <option value="">No pipelines yet</option>}
            {pipelines.map((pipeline) => (
              <option key={pipeline.id} value={pipeline.id}>
                {pipeline.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {scorecards.length > 0 && (
        <div className="card">
          <h3>Score trend</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Line type="monotone" dataKey="score" stroke="var(--accent)" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card">
        <h3>History</h3>
        {scorecards.length === 0 ? (
          <p className="muted">No scorecards yet — run this pipeline first.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Overall</th>
                <th>Completeness</th>
                <th>Consistency</th>
                <th>Accuracy</th>
                <th>Passed</th>
                <th>Δ</th>
              </tr>
            </thead>
            <tbody>
              {scorecards.map((s) => (
                <tr key={s.id}>
                  <td>{new Date(s.created_at).toLocaleString()}</td>
                  <td>{s.overall_score}</td>
                  <td>{s.completeness}</td>
                  <td>{s.consistency}</td>
                  <td>{s.accuracy}</td>
                  <td>{s.passed ? "Yes" : "No"}</td>
                  <td>{s.score_delta === null ? "—" : s.score_delta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function ScorecardsPage() {
  return (
    <WorkspaceGate>{(workspace) => <ScorecardsForWorkspace workspaceId={workspace.id} />}</WorkspaceGate>
  );
}
