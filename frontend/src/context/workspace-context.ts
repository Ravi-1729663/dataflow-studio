import { createContext } from "react";
import type { Workspace } from "../lib/types";

export interface WorkspaceContextValue {
  workspaces: Workspace[];
  current: Workspace | null;
  loading: boolean;
  selectWorkspace: (id: string) => void;
  createWorkspace: (name: string) => Promise<Workspace>;
  refresh: () => Promise<void>;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);
