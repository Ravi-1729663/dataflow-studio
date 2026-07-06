import { useState } from "react";
import type { FormEvent } from "react";
import { useWorkspace } from "../context/useWorkspace";

export function WorkspaceSwitcher() {
  const { workspaces, current, selectWorkspace, createWorkspace } = useWorkspace();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      await createWorkspace(name.trim());
      setName("");
      setCreating(false);
    } finally {
      setBusy(false);
    }
  };

  if (creating) {
    return (
      <form className="workspace-switcher-form" onSubmit={handleCreate}>
        <input
          autoFocus
          placeholder="Workspace name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !name.trim()}>
          Create
        </button>
        <button type="button" className="ghost" onClick={() => setCreating(false)} disabled={busy}>
          Cancel
        </button>
      </form>
    );
  }

  return (
    <div className="workspace-switcher">
      <select
        value={current?.id ?? ""}
        onChange={(e) => selectWorkspace(e.target.value)}
        aria-label="Select workspace"
      >
        {workspaces.length === 0 && <option value="">No workspaces</option>}
        {workspaces.map((ws) => (
          <option key={ws.id} value={ws.id}>
            {ws.name}
          </option>
        ))}
      </select>
      <button type="button" className="ghost" onClick={() => setCreating(true)}>
        + New
      </button>
    </div>
  );
}
