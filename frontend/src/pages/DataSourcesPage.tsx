import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { apiErrorMessage } from "../lib/api";
import { dataSources as dataSourcesApi } from "../lib/resources";
import type { DataSource, SourceType } from "../lib/types";
import { WorkspaceGate } from "../components/WorkspaceGate";

const SOURCE_TYPES: SourceType[] = ["FILE", "POSTGRES", "REST_API", "S3"];

interface ConfigField {
  key: string;
  label: string;
  placeholder: string;
  required?: boolean;
}

function configFieldsFor(sourceType: SourceType): ConfigField[] {
  switch (sourceType) {
    case "FILE":
      return [{ key: "path", label: "File path", placeholder: "sample_data/customers.csv" }];
    case "POSTGRES":
      return [
        { key: "dsn", label: "DSN", placeholder: "postgresql://user:pass@host/db" },
        { key: "query", label: "Query", placeholder: "SELECT * FROM customers" },
      ];
    case "REST_API":
      return [{ key: "url", label: "URL", placeholder: "https://api.example.com/customers" }];
    case "S3":
      return [
        { key: "bucket", label: "Bucket", placeholder: "my-bucket" },
        { key: "key", label: "Object key", placeholder: "customers.csv" },
        {
          key: "endpoint_url",
          label: "Endpoint URL (optional — leave blank for real AWS S3)",
          placeholder: "http://localhost:9000",
          required: false,
        },
        {
          key: "aws_access_key_id",
          label: "Access key ID (optional — leave blank to use IAM credentials)",
          placeholder: "minioadmin",
          required: false,
        },
        {
          key: "aws_secret_access_key",
          label: "Secret access key (optional)",
          placeholder: "minioadmin",
          required: false,
        },
      ];
  }
}

function NewDataSourceForm({
  workspaceId,
  onCreated,
}: {
  workspaceId: string;
  onCreated: (source: DataSource) => void;
}) {
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("FILE");
  const [configValues, setConfigValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const response = await dataSourcesApi.create({
        name,
        source_type: sourceType,
        config: configValues,
        workspace: workspaceId,
      });
      onCreated(response.data);
      setName("");
      setConfigValues({});
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <h3>New data source</h3>
      {error && <div className="alert alert-error">{error}</div>}
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Type
        <select
          value={sourceType}
          onChange={(e) => {
            setSourceType(e.target.value as SourceType);
            setConfigValues({});
          }}
        >
          {SOURCE_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </label>
      {configFieldsFor(sourceType).map((field) => (
        <label key={field.key}>
          {field.label}
          <input
            placeholder={field.placeholder}
            value={configValues[field.key] ?? ""}
            onChange={(e) => setConfigValues((prev) => ({ ...prev, [field.key]: e.target.value }))}
            required={field.required ?? true}
          />
        </label>
      ))}
      <button type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create data source"}
      </button>
    </form>
  );
}

function DataSourceRow({ source }: { source: DataSource }) {
  const [result, setResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const response = await dataSourcesApi.testConnection(source.id);
      setResult(response.data);
    } catch (err) {
      setResult({ ok: false, error: apiErrorMessage(err) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <tr>
      <td>{source.name}</td>
      <td>
        <span className="pill">{source.source_type}</span>
      </td>
      <td>{source.is_active ? "Active" : "Inactive"}</td>
      <td>
        <button type="button" className="ghost" onClick={handleTest} disabled={testing}>
          {testing ? "Testing…" : "Test connection"}
        </button>
        {result && (
          <span className={result.ok ? "test-ok" : "test-fail"}>
            {result.ok ? "OK" : (result.error ?? "Failed")}
          </span>
        )}
      </td>
    </tr>
  );
}

function DataSourcesForWorkspace({ workspaceId }: { workspaceId: string }) {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await dataSourcesApi.list(workspaceId);
      setSources(response.data.results);
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
      <h1>Data Sources</h1>
      <NewDataSourceForm workspaceId={workspaceId} onCreated={(s) => setSources((prev) => [s, ...prev])} />
      <div className="card">
        <h3>Existing data sources</h3>
        {error && <div className="alert alert-error">{error}</div>}
        {loading ? (
          <p>Loading…</p>
        ) : sources.length === 0 ? (
          <p className="muted">No data sources in this workspace yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <DataSourceRow key={source.id} source={source} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function DataSourcesPage() {
  return (
    <WorkspaceGate>{(workspace) => <DataSourcesForWorkspace workspaceId={workspace.id} />}</WorkspaceGate>
  );
}
