/**
 * HTTP client for the ApplySlave Python backend.
 *
 * Port is hard-coded in development because Vite runs on 1420 and the
 * Python server on 8765. In packaged builds the Rust shell launches the
 * backend on 8765 too, so the same URL works.
 */

import type {
  ApplicationsListResponse,
  DiscoverRequest,
  DiscoverResponse,
  DiscoveryTaskDetail,
  HealthResponse,
  ModelStatusResponse,
  SubmitBatchResponse,
  UserProfile,
} from "../types/api";

const BACKEND_URL = "http://localhost:8765";

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${BACKEND_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(
      `${init?.method ?? "GET"} ${path} → ${response.status}${body ? `: ${body}` : ""}`,
    );
  }
  // 204s etc.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const backendClient = {
  getHealth: () => request<HealthResponse>("/api/health"),
  getModelStatus: () => request<ModelStatusResponse>("/api/model/status"),
  startModelDownload: () =>
    request<{ task_id: string }>("/api/model/download", {
      method: "POST",
    }),

  getProfile: () => request<UserProfile | null>("/api/profile"),
  saveProfile: (profile: UserProfile) =>
    request<UserProfile>("/api/profile", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(profile),
    }),
  uploadResume: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<{ path: string; parsed_fields: Record<string, string | null> }>(
      "/api/profile/resume",
      { method: "POST", body: formData },
    );
  },

  startDiscovery: (payload: DiscoverRequest) =>
    request<DiscoverResponse>("/api/jobs/discover", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getDiscoveryTask: (taskId: string) =>
    request<DiscoveryTaskDetail>(`/api/jobs/discover/${taskId}`),

  listApplications: (status?: string) => {
    const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<ApplicationsListResponse>(`/api/applications${suffix}`);
  },
  submitBatch: (
    jobs: Array<{ url: string; company: string; title: string }>,
  ) =>
    request<SubmitBatchResponse>("/api/applications", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ jobs }),
    }),
};

export function openWebSocket(
  onMessage: (event: MessageEvent) => void,
): WebSocket {
  const ws = new WebSocket(`${BACKEND_URL.replace("http", "ws")}/api/ws`);
  ws.onmessage = onMessage;
  return ws;
}
