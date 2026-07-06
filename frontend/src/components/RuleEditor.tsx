import type { Severity, ValidationRule } from "../lib/types";

const RULE_TYPES: ValidationRule["type"][] = [
  "required_columns",
  "not_null",
  "unique",
  "no_duplicate_rows",
  "column_type",
  "range",
  "allowed_values",
  "freshness",
  "business_rule",
];

const COLUMNS_TYPES = new Set(["required_columns", "not_null", "unique"]);
const SINGLE_COLUMN_TYPES = new Set(["column_type", "range", "allowed_values", "freshness"]);

function defaultsFor(type: ValidationRule["type"]): ValidationRule {
  if (COLUMNS_TYPES.has(type)) return { type, columns: [] };
  if (SINGLE_COLUMN_TYPES.has(type)) return { type, column: "" };
  if (type === "business_rule") return { type, name: "business_rule", expression: "" };
  return { type };
}

export function RuleEditor({
  rule,
  onChange,
  onRemove,
}: {
  rule: ValidationRule;
  onChange: (rule: ValidationRule) => void;
  onRemove: () => void;
}) {
  const set = <K extends keyof ValidationRule>(key: K, value: ValidationRule[K]) =>
    onChange({ ...rule, [key]: value });

  return (
    <div className="rule-editor">
      <select value={rule.type} onChange={(e) => onChange(defaultsFor(e.target.value as ValidationRule["type"]))}>
        {RULE_TYPES.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>

      {COLUMNS_TYPES.has(rule.type) && (
        <input
          placeholder="columns (comma-separated)"
          value={(rule.columns ?? []).join(",")}
          onChange={(e) =>
            set(
              "columns",
              e.target.value.split(",").map((c) => c.trim()).filter(Boolean),
            )
          }
        />
      )}

      {SINGLE_COLUMN_TYPES.has(rule.type) && (
        <input
          placeholder="column"
          value={rule.column ?? ""}
          onChange={(e) => set("column", e.target.value)}
        />
      )}

      {rule.type === "column_type" && (
        <input
          placeholder="expected type (int/float)"
          value={rule.expected_type ?? ""}
          onChange={(e) => set("expected_type", e.target.value)}
        />
      )}

      {rule.type === "range" && (
        <>
          <input
            type="number"
            placeholder="min"
            value={rule.min ?? ""}
            onChange={(e) => set("min", e.target.value === "" ? undefined : Number(e.target.value))}
          />
          <input
            type="number"
            placeholder="max"
            value={rule.max ?? ""}
            onChange={(e) => set("max", e.target.value === "" ? undefined : Number(e.target.value))}
          />
        </>
      )}

      {rule.type === "allowed_values" && (
        <input
          placeholder="allowed values (comma-separated)"
          value={(rule.values ?? []).join(",")}
          onChange={(e) =>
            set(
              "values",
              e.target.value.split(",").map((v) => v.trim()).filter(Boolean),
            )
          }
        />
      )}

      {rule.type === "freshness" && (
        <input
          type="number"
          placeholder="max age (days)"
          value={rule.max_age_days ?? ""}
          onChange={(e) =>
            set("max_age_days", e.target.value === "" ? undefined : Number(e.target.value))
          }
        />
      )}

      {rule.type === "business_rule" && (
        <>
          <input
            placeholder="rule name"
            value={rule.name ?? ""}
            onChange={(e) => set("name", e.target.value)}
          />
          <input
            placeholder="pandas expression, e.g. age >= 0"
            value={rule.expression ?? ""}
            onChange={(e) => set("expression", e.target.value)}
          />
        </>
      )}

      <select
        value={rule.severity ?? "blocking"}
        onChange={(e) => set("severity", e.target.value as Severity)}
      >
        <option value="blocking">blocking</option>
        <option value="warning">warning</option>
      </select>

      <button type="button" className="ghost" onClick={onRemove}>
        Remove
      </button>
    </div>
  );
}
