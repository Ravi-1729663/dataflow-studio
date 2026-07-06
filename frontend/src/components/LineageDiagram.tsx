import type { LineageGraph, MedallionLayer } from "../lib/types";

const LAYER_ORDER: MedallionLayer[] = ["SOURCE", "BRONZE", "SILVER", "GOLD"];
const COLUMN_WIDTH = 220;
const ROW_HEIGHT = 80;
const NODE_WIDTH = 160;
const NODE_HEIGHT = 44;

function nodeKey(layer: string, name: string) {
  return `${layer}::${name}`;
}

export function LineageDiagram({ graph }: { graph: LineageGraph }) {
  const nodesByLayer = new Map<MedallionLayer, typeof graph.nodes>();
  for (const layer of LAYER_ORDER) nodesByLayer.set(layer, []);
  for (const node of graph.nodes) {
    nodesByLayer.get(node.layer)?.push(node);
  }

  const positions = new Map<string, { x: number; y: number }>();
  LAYER_ORDER.forEach((layer, colIndex) => {
    const nodes = nodesByLayer.get(layer) ?? [];
    nodes.forEach((node, rowIndex) => {
      positions.set(nodeKey(layer, node.name), {
        x: colIndex * COLUMN_WIDTH + 20,
        y: rowIndex * ROW_HEIGHT + 30,
      });
    });
  });

  const maxRows = Math.max(1, ...LAYER_ORDER.map((layer) => (nodesByLayer.get(layer) ?? []).length));
  const width = LAYER_ORDER.length * COLUMN_WIDTH;
  const height = maxRows * ROW_HEIGHT + 60;

  return (
    <svg className="lineage-svg" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="var(--muted)" />
        </marker>
      </defs>

      {LAYER_ORDER.map((layer, colIndex) => (
        <text key={layer} x={colIndex * COLUMN_WIDTH + 20} y={16} className="lineage-layer-label">
          {layer}
        </text>
      ))}

      {graph.edges.map((edge, index) => {
        const from = positions.get(nodeKey(edge.from.layer, edge.from.name));
        const to = positions.get(nodeKey(edge.to.layer, edge.to.name));
        if (!from || !to) return null;
        const x1 = from.x + NODE_WIDTH;
        const y1 = from.y + NODE_HEIGHT / 2;
        const x2 = to.x;
        const y2 = to.y + NODE_HEIGHT / 2;
        const midX = (x1 + x2) / 2;
        return (
          <g key={index}>
            <path
              d={`M${x1},${y1} C${midX},${y1} ${midX},${y2} ${x2},${y2}`}
              fill="none"
              stroke="var(--muted)"
              strokeWidth={1.5}
              markerEnd="url(#arrow)"
            />
            <text x={midX} y={(y1 + y2) / 2 - 6} className="lineage-edge-label">
              {edge.pipeline}
            </text>
          </g>
        );
      })}

      {graph.nodes.map((node) => {
        const pos = positions.get(nodeKey(node.layer, node.name));
        if (!pos) return null;
        return (
          <g key={nodeKey(node.layer, node.name)} transform={`translate(${pos.x}, ${pos.y})`}>
            <rect width={NODE_WIDTH} height={NODE_HEIGHT} rx={8} className={`lineage-node lineage-node-${node.layer.toLowerCase()}`} />
            <text x={NODE_WIDTH / 2} y={NODE_HEIGHT / 2 + 5} textAnchor="middle" className="lineage-node-label">
              {node.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
