/**
 * HTTP client for the ApplySlave Python backend.
 *
 * The port comes from the Tauri shell via `invoke('backend_port')` when
 * running inside Tauri. When the frontend is loaded in a plain browser
 * (e.g. via `pnpm exec vite`), we fall back to the dev default 8765.
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

const DEFAULT_BACKEND_PORT = 8765;

async function resolveBackendUrl(): Promise<string> {
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const port = await invoke<number>("backend_port");
      return `http://localhost:${port}`;
    } catch (error) {
      console.warn("Failed to resolve backend port via Tauri, using default", error);
    }
  }
  return `http://localhost:${DEFAULT_BACKEND_PORT}`;
}

let backendUrlPromise: Promise<string> | null = null;
function getBackendUrl(): Promise<string> {
  if (backendUrlPromise === null) {
    backendUrlPromise = resolveBackendUrl();
  }
  return backendUrlPromise;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const baseUrl = await getBackendUrl();
  const response = await fetch(`${baseUrl}${path}`, init);
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(
      `${init?.method ?? "GET"} ${path} → ${response.status}${body ? `: ${body}` : ""}`,
    );
  }
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
    return request<{
      path: string;
      llm_used: boolean;
      llm_error?: string | null;
      profile: UserProfile | null;
      parsed_fields: Record<string, string | null>;
    }>("/api/profile/resume", { method: "POST", body: formData });
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
): Promise<WebSocket> {
  return getBackendUrl().then((baseUrl) => {
    const ws = new WebSocket(`${baseUrl.replace("http", "ws")}/api/ws`);
    ws.onmessage = onMessage;
    return ws;
  });
}
