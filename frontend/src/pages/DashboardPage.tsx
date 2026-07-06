import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiErrorMessage } from "../lib/api";
import { metadata, monitoring } from "../lib/resources";
import type { ColumnAnomaly, DashboardStats } from "../lib/types";

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [anomalies, setAnomalies] = useState<ColumnAnomaly[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    monitoring
      .dashboard()
      .then((response) => setStats(response.data))
      .catch((err: unknown) => setError(apiErrorMessage(err)));
    metadata
      .anomalies()
      .then((response) => setAnomalies(response.data.results))
      .catch(() => {
        // Non-critical panel — the dashboard still works without it.
      });
  }, []);

  if (error) return <div className="alert alert-error">{error}</div>;
  if (!stats) return <div className="page-loading">Loading…</div>;

  const chartData = [
    { name: "Succeeded", count: stats.succeeded },
    { name: "Failed", count: stats.failed },
    { name: "Retrying", count: stats.retrying },
    { name: "Pending/Running", count: stats.pending_or_running },
  ];

  return (
    <div className="page">
      <h1>Dashboard</h1>
      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-value">{stats.total_runs}</span>
          <span className="stat-label">Total runs</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {stats.success_rate_percent === null ? "—" : `${stats.success_rate_percent}%`}
          </span>
          <span className="stat-label">Success rate</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {stats.avg_duration_seconds === null ? "—" : `${stats.avg_duration_seconds}s`}
          </span>
          <span className="stat-label">Avg duration</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{stats.failed}</span>
          <span className="stat-label">Failed runs</span>
        </div>
      </div>

      <div className="card">
        <h3>Run outcomes</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="card">
        <h3>Recent failed jobs</h3>
        {stats.failed_jobs.length === 0 ? (
          <p className="muted">No failed jobs. 🎉</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Pipeline</th>
                <th>Error</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {stats.failed_jobs.map((job) => (
                <tr key={job.run_id}>
                  <td>{job.pipeline}</td>
                  <td className="error-cell">{job.error}</td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>Data anomalies</h3>
        <p className="muted" style={{ marginBottom: 12 }}>
          Numeric columns whose mean drifted more than 3 standard deviations from their running
          baseline on ingest.
        </p>
        {anomalies.length === 0 ? (
          <p className="muted">No anomalies detected yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Column</th>
                <th>Value</th>
                <th>Baseline</th>
                <th>Z-score</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.map((anomaly) => (
                <tr key={anomaly.id}>
                  <td>{anomaly.dataset}</td>
                  <td>{anomaly.column}</td>
                  <td>{anomaly.value.toFixed(2)}</td>
                  <td>
                    {anomaly.baseline_mean.toFixed(2)} ± {anomaly.baseline_stddev.toFixed(2)}
                  </td>
                  <td>{anomaly.z_score.toFixed(2)}</td>
                  <td>{new Date(anomaly.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
