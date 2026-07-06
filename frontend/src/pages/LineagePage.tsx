import { useEffect, useState } from "react";
import { apiErrorMessage } from "../lib/api";
import { metadata } from "../lib/resources";
import type { Dataset, LineageGraph } from "../lib/types";
import { LineageDiagram } from "../components/LineageDiagram";

export function LineagePage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState("");
  const [graph, setGraph] = useState<LineageGraph | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    metadata
      .datasets()
      .then((response) => {
        setDatasets(response.data.results);
        setSelected((prev) => prev || (response.data.results[0]?.name ?? ""));
      })
      .catch((err: unknown) => setError(apiErrorMessage(err)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setGraph(null);
    metadata
      .lineage(selected)
      .then((response) => setGraph(response.data))
      .catch((err: unknown) => setError(apiErrorMessage(err)));
  }, [selected]);

  return (
    <div className="page">
      <h1>Lineage</h1>
      <div className="card">
        <label>
          Dataset
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {datasets.length === 0 && <option value="">No datasets yet</option>}
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.name}>
                {dataset.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {graph && (
        <div className="card lineage-card">
          <h3>{graph.dataset}</h3>
          {graph.nodes.length === 0 ? (
            <p className="muted">No lineage recorded yet — run a pipeline feeding this dataset.</p>
          ) : (
            <div className="lineage-scroll">
              <LineageDiagram graph={graph} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
