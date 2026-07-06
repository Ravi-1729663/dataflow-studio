import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { workspaces as workspacesApi } from "../lib/resources";
import type { Workspace } from "../lib/types";
import { useAuth } from "./useAuth";
import { WorkspaceContext } from "./workspace-context";

const SELECTED_WORKSPACE_KEY = "dataflow.workspace";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(
    localStorage.getItem(SELECTED_WORKSPACE_KEY),
  );
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const response = await workspacesApi.list();
    setWorkspaces(response.data.results);
    setCurrentId((prev) => {
      if (prev && response.data.results.some((w) => w.id === prev)) return prev;
      return response.data.results[0]?.id ?? null;
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!user) {
      setWorkspaces([]);
      setCurrentId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    void refresh();
  }, [user, refresh]);

  const selectWorkspace = useCallback((id: string) => {
    setCurrentId(id);
    localStorage.setItem(SELECTED_WORKSPACE_KEY, id);
  }, []);

  const createWorkspace = useCallback(
    async (name: string) => {
      const response = await workspacesApi.create(name);
      setWorkspaces((prev) => [...prev, response.data]);
      selectWorkspace(response.data.id);
      return response.data;
    },
    [selectWorkspace],
  );

  const current = useMemo(
    () => workspaces.find((w) => w.id === currentId) ?? null,
    [workspaces, currentId],
  );

  const value = useMemo(
    () => ({ workspaces, current, loading, selectWorkspace, createWorkspace, refresh }),
    [workspaces, current, loading, selectWorkspace, createWorkspace, refresh],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
