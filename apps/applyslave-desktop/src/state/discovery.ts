/**
 * Module-global search state for the Discovery page.
 *
 * React's useState lives on the component, so navigating away from the page
 * unmounts and loses everything. This module keeps the last query, task id,
 * and selected jobs alive across page navigations.
 *
 * Tiny pub/sub so React components can subscribe via useSyncExternalStore.
 */

export type SortMode = "relevance" | "date" | "company";

export interface DiscoveryState {
  keywords: string;
  location: string;
  remoteOnly: boolean;
  experienceLevels: string[];
  activeTaskId: string | null;
  selectedJobIds: ReadonlySet<string>;
  sortMode: SortMode;
}

let state: DiscoveryState = {
  keywords: "",
  location: "",
  remoteOnly: false,
  experienceLevels: [],
  activeTaskId: null,
  selectedJobIds: new Set<string>(),
  sortMode: "relevance",
};

const listeners = new Set<() => void>();

export function getDiscoveryState(): DiscoveryState {
  return state;
}

export function subscribeDiscoveryState(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setDiscoveryState(patch: Partial<DiscoveryState>): void {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

export function toggleSelectedJob(jobId: string): void {
  const next = new Set(state.selectedJobIds);
  if (next.has(jobId)) {
    next.delete(jobId);
  } else {
    next.add(jobId);
  }
  setDiscoveryState({ selectedJobIds: next });
}

export function clearSelectedJobs(): void {
  setDiscoveryState({ selectedJobIds: new Set() });
}
