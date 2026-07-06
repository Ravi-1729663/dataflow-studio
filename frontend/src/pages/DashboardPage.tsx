import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiErrorMessage } from "../lib/api";
import { monitoring } from "../lib/resources";
import type { DashboardStats } from "../lib/types";

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    monitoring
      .dashboard()
      .then((response) => setStats(response.data))
      .catch((err: unknown) => setError(apiErrorMessage(err)));
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
    </div>
  );
}
