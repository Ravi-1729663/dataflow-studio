import { api } from "./api";
import type {
  DashboardStats,
  DataSource,
  Dataset,
  DeadLetterRecord,
  LineageGraph,
  Paginated,
  Pipeline,
  PipelineRun,
  QualityScorecard,
  User,
  Workspace,
  WorkspaceMembership,
} from "./types";

export const auth = {
  register: (payload: { username: string; email: string; password: string }) =>
    api.post<User>("/auth/register/", payload),
  login: (username: string, password: string) =>
    api.post<{ access: string; refresh: string }>("/auth/token/", { username, password }),
  me: () => api.get<User>("/auth/me/"),
};

export const workspaces = {
  list: () => api.get<Paginated<Workspace>>("/workspaces/"),
  create: (name: string) => api.post<Workspace>("/workspaces/", { name }),
  members: (workspaceId: string) =>
    api.get<WorkspaceMembership[]>(`/workspaces/${workspaceId}/members/`),
  addMember: (workspaceId: string, username: string) =>
    api.post<WorkspaceMembership>(`/workspaces/${workspaceId}/members/`, { username }),
  removeMember: (workspaceId: string, userId: number) =>
    api.delete(`/workspaces/${workspaceId}/members/${userId}/`),
};

export const dataSources = {
  list: (workspaceId: string) =>
    api.get<Paginated<DataSource>>("/datasources/", { params: { workspace: workspaceId } }),
  create: (payload: Partial<DataSource>) => api.post<DataSource>("/datasources/", payload),
  remove: (id: string) => api.delete(`/datasources/${id}/`),
  testConnection: (id: string) =>
    api.post<{ ok: boolean; error?: string }>(`/datasources/${id}/test-connection/`),
};

export const pipelines = {
  list: (workspaceId: string) =>
    api.get<Paginated<Pipeline>>("/pipelines/", { params: { workspace: workspaceId } }),
  get: (id: string) => api.get<Pipeline>(`/pipelines/${id}/`),
  create: (payload: Partial<Pipeline>) => api.post<Pipeline>("/pipelines/", payload),
  run: (id: string) => api.post<PipelineRun>(`/pipelines/${id}/run/`),
  clone: (id: string) => api.post<Pipeline>(`/pipelines/${id}/clone/`),
  pause: (id: string) => api.post<Pipeline>(`/pipelines/${id}/pause/`),
  resume: (id: string) => api.post<Pipeline>(`/pipelines/${id}/resume/`),
  runs: (pipelineId: string) =>
    api.get<Paginated<PipelineRun>>("/pipelines/runs/", { params: { pipeline: pipelineId } }),
  getRun: (runId: string) => api.get<PipelineRun>(`/pipelines/runs/${runId}/`),
};

export const scheduler = {
  queue: () => api.get<PipelineRun[]>("/scheduler/queue/"),
  deadLetter: () => api.get<Paginated<DeadLetterRecord>>("/scheduler/dead-letter/"),
  retry: (runId: string) => api.post<PipelineRun>(`/scheduler/runs/${runId}/retry/`),
};

export const validation = {
  scorecards: (pipelineId: string) =>
    api.get<Paginated<QualityScorecard>>("/validation/scorecards/", {
      params: { run__pipeline: pipelineId },
    }),
};

export const metadata = {
  datasets: () => api.get<Paginated<Dataset>>("/metadata/datasets/"),
  lineage: (datasetName: string) =>
    api.get<LineageGraph>(`/metadata/datasets/${datasetName}/lineage/`),
};

export const monitoring = {
  dashboard: () => api.get<DashboardStats>("/monitoring/dashboard/"),
};
