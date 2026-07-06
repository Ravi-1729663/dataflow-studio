import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiErrorMessage } from "../lib/api";
import { dataSources as dataSourcesApi, pipelines as pipelinesApi } from "../lib/resources";
import type { CleanConfig, DataSource, PipelineConfig, ValidationRule } from "../lib/types";
import { RuleEditor } from "../components/RuleEditor";
import { WorkspaceGate } from "../components/WorkspaceGate";

const TARGETS = [
  { value: "customers", label: "customers (Type-1 upsert)" },
  { value: "customers_scd2", label: "customers_scd2 (SCD Type 2 history)" },
];

function PipelineBuilder({ workspaceId }: { workspaceId: string }) {
  const navigate = useNavigate();
  const [sources, setSources] = useState<DataSource[]>([]);
  const [name, setName] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [schedule, setSchedule] = useState("");
  const [target, setTarget] = useState(TARGETS[0].value);
  const [rules, setRules] = useState<ValidationRule[]>([
    { type: "required_columns", columns: [], severity: "blocking" },
  ]);
  const [renamePairs, setRenamePairs] = useState<Array<{ from: string; to: string }>>([]);
  const [incrementalColumn, setIncrementalColumn] = useState("");
  const [trimColumns, setTrimColumns] = useState("");
  const [lowercaseColumns, setLowercaseColumns] = useState("");
  const [fillNullPairs, setFillNullPairs] = useState<Array<{ column: string; value: string }>>([]);
  const [dropRowsMissing, setDropRowsMissing] = useState("");
  const [minPresentFraction, setMinPresentFraction] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void dataSourcesApi.list(workspaceId).then((response) => {
      setSources(response.data.results);
      setSourceId((prev) => prev || (response.data.results[0]?.id ?? ""));
    });
  }, [workspaceId]);

  const addRule = () => setRules((prev) => [...prev, { type: "not_null", columns: [] }]);
  const updateRule = (index: number, rule: ValidationRule) =>
    setRules((prev) => prev.map((r, i) => (i === index ? rule : r)));
  const removeRule = (index: number) => setRules((prev) => prev.filter((_, i) => i !== index));

  const addRenamePair = () => setRenamePairs((prev) => [...prev, { from: "", to: "" }]);
  const updateRenamePair = (index: number, field: "from" | "to", value: string) =>
    setRenamePairs((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)));
  const removeRenamePair = (index: number) =>
    setRenamePairs((prev) => prev.filter((_, i) => i !== index));

  const addFillNullPair = () => setFillNullPairs((prev) => [...prev, { column: "", value: "" }]);
  const updateFillNullPair = (index: number, field: "column" | "value", value: string) =>
    setFillNullPairs((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)));
  const removeFillNullPair = (index: number) =>
    setFillNullPairs((prev) => prev.filter((_, i) => i !== index));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!sourceId) {
      setError("select a data source");
      return;
    }
    setBusy(true);
    try {
      const parseColumnsList = (s: string) =>
        s.split(",").map((c) => c.trim()).filter(Boolean);

      const clean: CleanConfig = {};
      const trimList = parseColumnsList(trimColumns);
      if (trimList.length) clean.trim = trimList;
      const lowercaseList = parseColumnsList(lowercaseColumns);
      if (lowercaseList.length) clean.lowercase = lowercaseList;
      const fillNullEntries = fillNullPairs.filter((p) => p.column && p.value);
      if (fillNullEntries.length) {
        clean.fill_null = Object.fromEntries(fillNullEntries.map((p) => [p.column, p.value]));
      }
      const dropList = parseColumnsList(dropRowsMissing);
      if (dropList.length) clean.drop_rows_missing = dropList;
      if (minPresentFraction) clean.min_present_fraction = Number(minPresentFraction);

      const config: PipelineConfig = {
        validation: { rules },
        transform: {
          rename: Object.fromEntries(
            renamePairs.filter((p) => p.from && p.to).map((p) => [p.from, p.to]),
          ),
          ...(Object.keys(clean).length ? { clean } : {}),
        },
        target,
        ...(incrementalColumn ? { incremental: { column: incrementalColumn } } : {}),
      };
      const response = await pipelinesApi.create({
        name,
        source: sourceId,
        schedule,
        config,
      });
      navigate(`/pipelines/${response.data.id}`);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <h1>New pipeline</h1>
      <form className="card form" onSubmit={handleSubmit}>
        {error && <div className="alert alert-error">{error}</div>}
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Source
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)} required>
            <option value="" disabled>
              Select a data source
            </option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name} ({source.source_type})
              </option>
            ))}
          </select>
        </label>
        {sources.length === 0 && (
          <p className="muted">No data sources yet — create one on the Data Sources page first.</p>
        )}
        <label>
          Schedule (cron, optional)
          <input
            placeholder="*/5 * * * *"
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
          />
        </label>
        <label>
          Target
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {TARGETS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Incremental column (optional)
          <input
            placeholder="e.g. updated_at"
            value={incrementalColumn}
            onChange={(e) => setIncrementalColumn(e.target.value)}
          />
        </label>

        <fieldset>
          <legend>Data cleansing (optional — runs before validation, so a fixable row doesn't block the whole run)</legend>
          <label>
            Trim whitespace on columns
            <input
              placeholder="email, first_name"
              value={trimColumns}
              onChange={(e) => setTrimColumns(e.target.value)}
            />
          </label>
          <label>
            Lowercase columns
            <input
              placeholder="email"
              value={lowercaseColumns}
              onChange={(e) => setLowercaseColumns(e.target.value)}
            />
          </label>
          <label>
            Drop rows missing any of these columns
            <input
              placeholder="email"
              value={dropRowsMissing}
              onChange={(e) => setDropRowsMissing(e.target.value)}
            />
          </label>
          <label>
            Drop rows with less than this fraction of columns populated (0-1, optional)
            <input
              type="number"
              min={0}
              max={1}
              step={0.1}
              placeholder="0.5"
              value={minPresentFraction}
              onChange={(e) => setMinPresentFraction(e.target.value)}
            />
          </label>
          <label>Fill missing values with a default</label>
          {fillNullPairs.map((pair, index) => (
            <div key={index} className="rename-pair">
              <input
                placeholder="column"
                value={pair.column}
                onChange={(e) => updateFillNullPair(index, "column", e.target.value)}
              />
              <input
                placeholder="default value"
                value={pair.value}
                onChange={(e) => updateFillNullPair(index, "value", e.target.value)}
              />
              <button type="button" className="ghost" onClick={() => removeFillNullPair(index)}>
                Remove
              </button>
            </div>
          ))}
          <button type="button" className="ghost" onClick={addFillNullPair}>
            + Add fill-null default
          </button>
        </fieldset>

        <fieldset>
          <legend>Validation rules</legend>
          {rules.map((rule, index) => (
            <RuleEditor
              key={index}
              rule={rule}
              onChange={(r) => updateRule(index, r)}
              onRemove={() => removeRule(index)}
            />
          ))}
          <button type="button" className="ghost" onClick={addRule}>
            + Add rule
          </button>
        </fieldset>

        <fieldset>
          <legend>Rename columns (optional)</legend>
          {renamePairs.map((pair, index) => (
            <div key={index} className="rename-pair">
              <input
                placeholder="from"
                value={pair.from}
                onChange={(e) => updateRenamePair(index, "from", e.target.value)}
              />
              <input
                placeholder="to"
                value={pair.to}
                onChange={(e) => updateRenamePair(index, "to", e.target.value)}
              />
              <button type="button" className="ghost" onClick={() => removeRenamePair(index)}>
                Remove
              </button>
            </div>
          ))}
          <button type="button" className="ghost" onClick={addRenamePair}>
            + Add rename
          </button>
        </fieldset>

        <button type="submit" disabled={busy || !sourceId}>
          {busy ? "Creating…" : "Create pipeline"}
        </button>
      </form>
    </div>
  );
}

export function PipelineNewPage() {
  return <WorkspaceGate>{(workspace) => <PipelineBuilder workspaceId={workspace.id} />}</WorkspaceGate>;
}
