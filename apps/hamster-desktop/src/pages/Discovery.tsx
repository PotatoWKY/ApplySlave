import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useSyncExternalStore } from "react";

import { JobRow } from "../components/JobRow";
import { backendClient } from "../services/backend";
import {
  clearSelectedJobs,
  getDiscoveryState,
  setDiscoveryState,
  subscribeDiscoveryState,
  toggleSelectedJob,
} from "../state/discovery";
import type { JobListing, RecommendedLevels } from "../types/api";

function useDiscoveryState() {
  return useSyncExternalStore(subscribeDiscoveryState, getDiscoveryState);
}

export function DiscoveryPage() {
  const queryClient = useQueryClient();
  const {
    keywords,
    location,
    remoteOnly,
    experienceLevels,
    activeTaskId,
    selectedJobIds,
    sortMode,
  } = useDiscoveryState();

  const suggestionsQuery = useQuery({
    queryKey: ["suggested-searches"],
    queryFn: backendClient.getSuggestedSearches,
  });

  const levelsQuery = useQuery({
    queryKey: ["recommended-levels"],
    queryFn: backendClient.getRecommendedLevels,
  });

  // Set default keywords from suggestions on first load (only if empty)
  useEffect(() => {
    const current = getDiscoveryState();
    if (
      suggestionsQuery.data?.suggestions?.length &&
      current.keywords === ""
    ) {
      setDiscoveryState({ keywords: suggestionsQuery.data.suggestions[0] });
    }
  }, [suggestionsQuery.data]);

  // Default-select recommended levels on first load
  useEffect(() => {
    const current = getDiscoveryState();
    if (
      levelsQuery.data?.recommended &&
      current.experienceLevels.length === 0
    ) {
      setDiscoveryState({
        experienceLevels: [...levelsQuery.data.recommended],
      });
    }
  }, [levelsQuery.data]);

  const startMutation = useMutation({
    mutationFn: backendClient.startDiscovery,
    onMutate: () => {
      // Clear old results immediately so the user doesn't see stale data
      // while the new search is running.
      setDiscoveryState({ activeTaskId: null });
      clearSelectedJobs();
    },
    onSuccess: (response) => {
      setDiscoveryState({ activeTaskId: response.task_id });
    },
  });

  const taskQuery = useQuery({
    queryKey: ["discoveryTask", activeTaskId],
    queryFn: () =>
      activeTaskId ? backendClient.getDiscoveryTask(activeTaskId) : null,
    enabled: activeTaskId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || data.status === "completed" || data.status === "failed") {
        return false;
      }
      return 2000;
    },
  });

  const submitMutation = useMutation({
    mutationFn: backendClient.submitBatch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      clearSelectedJobs();
    },
  });

  const rawJobs: JobListing[] = taskQuery.data?.results ?? [];

  const sortedJobs = useMemo(() => {
    const copy = [...rawJobs];
    switch (sortMode) {
      case "relevance":
        copy.sort(
          (jobA, jobB) => (jobB.relevance_score ?? 0) - (jobA.relevance_score ?? 0),
        );
        break;
      case "date":
        copy.sort((jobA, jobB) => {
          const dateA = jobA.posted_at ?? "";
          const dateB = jobB.posted_at ?? "";
          return dateB.localeCompare(dateA);
        });
        break;
      case "company":
        copy.sort((jobA, jobB) => jobA.company.localeCompare(jobB.company));
        break;
    }
    return copy;
  }, [rawJobs, sortMode]);

  const submitSelected = () => {
    const selected = sortedJobs.filter((job) => selectedJobIds.has(job.id));
    if (selected.length === 0) return;
    submitMutation.mutate(selected);
  };

  const suggestions = suggestionsQuery.data?.suggestions ?? [];

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-medium">Discover jobs</h2>

        {suggestions.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => setDiscoveryState({ keywords: suggestion })}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  keywords === suggestion
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-300 text-slate-600 hover:bg-slate-50"
                }`}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <label className="block sm:col-span-2">
            <span className="text-sm font-medium text-slate-700">Keywords</span>
            <input
              value={keywords}
              onChange={(event) =>
                setDiscoveryState({ keywords: event.target.value })
              }
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Location</span>
            <input
              value={location}
              onChange={(event) =>
                setDiscoveryState({ location: event.target.value })
              }
              placeholder="Seattle, remote, …"
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
            />
          </label>
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={remoteOnly}
            onChange={(event) =>
              setDiscoveryState({ remoteOnly: event.target.checked })
            }
          />
          Remote only
        </label>

        <LevelFilter
          levels={levelsQuery.data}
          selected={experienceLevels}
          onChange={(next) =>
            setDiscoveryState({ experienceLevels: next })
          }
        />

        <div className="mt-4">
          <button
            type="button"
            onClick={() =>
              startMutation.mutate({
                keywords,
                location,
                remote_only: remoteOnly,
                exclude_companies: [],
                experience_levels: experienceLevels,
                max_results: 100,
              })
            }
            disabled={startMutation.isPending || !keywords.trim()}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
          >
            {startMutation.isPending ? "Searching…" : "Search"}
          </button>
        </div>
      </section>

      {activeTaskId && (
        <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
          <header className="flex items-center justify-between gap-4">
            <h2 className="text-xl font-medium">
              Results
              {taskQuery.data?.status && (
                <span className="ml-2 text-sm font-normal text-slate-500">
                  ({taskQuery.data.status}
                  {sortedJobs.length > 0 && ` · ${sortedJobs.length} jobs`})
                </span>
              )}
            </h2>
            <button
              type="button"
              disabled={selectedJobIds.size === 0 || submitMutation.isPending}
              onClick={submitSelected}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-emerald-500 disabled:opacity-50"
            >
              {submitMutation.isPending
                ? "Queueing…"
                : `Queue ${selectedJobIds.size} selected`}
            </button>
          </header>

          {sortedJobs.length > 0 && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <span className="text-slate-500">Sort by:</span>
              <SortButton
                active={sortMode === "relevance"}
                onClick={() => setDiscoveryState({ sortMode: "relevance" })}
              >
                Relevance
              </SortButton>
              <SortButton
                active={sortMode === "date"}
                onClick={() => setDiscoveryState({ sortMode: "date" })}
              >
                Date posted
              </SortButton>
              <SortButton
                active={sortMode === "company"}
                onClick={() => setDiscoveryState({ sortMode: "company" })}
              >
                Company
              </SortButton>
            </div>
          )}

          {sortedJobs.length === 0 && taskQuery.data?.status === "completed" ? (
            <p className="mt-3 text-sm text-slate-500">
              No jobs matched the query.
            </p>
          ) : (
            <JobList jobs={sortedJobs} selected={selectedJobIds} />
          )}
        </section>
      )}
    </div>
  );
}

function LevelFilter({
  levels,
  selected,
  onChange,
}: {
  levels: RecommendedLevels | undefined;
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const allLevels = ["intern", "entry", "mid", "senior", "lead"];
  const labels: Record<string, string> = {
    intern: "Intern",
    entry: "Entry",
    mid: "Mid",
    senior: "Senior",
    lead: "Lead+",
  };

  const recommended = new Set(levels?.recommended ?? []);
  const stretch = new Set(levels?.stretch ?? []);

  const toggle = (level: string) => {
    if (selected.includes(level)) {
      onChange(selected.filter((current) => current !== level));
    } else {
      onChange([...selected, level]);
    }
  };

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium text-slate-700">Levels:</span>
        {allLevels.map((level) => {
          const isSelected = selected.includes(level);
          const tag = recommended.has(level)
            ? "rec"
            : stretch.has(level)
              ? "stretch"
              : "off";
          return (
            <button
              key={level}
              type="button"
              onClick={() => toggle(level)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                isSelected
                  ? "border-slate-900 bg-slate-900 text-white"
                  : tag === "rec"
                    ? "border-green-300 bg-green-50 text-green-700 hover:bg-green-100"
                    : tag === "stretch"
                      ? "border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100"
                      : "border-slate-200 bg-slate-50 text-slate-400 hover:bg-slate-100"
              }`}
              title={
                tag === "rec"
                  ? "Recommended for your profile"
                  : tag === "stretch"
                    ? "Stretch — possible but not a strong fit"
                    : "Off-target — likely under/over qualified"
              }
            >
              {labels[level]}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => onChange([])}
          className="ml-auto text-xs text-slate-500 hover:underline"
        >
          Clear filter
        </button>
      </div>
      {levels?.reasoning && (
        <div className="mt-1.5 text-xs text-slate-500">
          {levels.reasoning}
        </div>
      )}
    </div>
  );
}

function SortButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
        active
          ? "bg-slate-900 text-white"
          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

function JobList({
  jobs,
  selected,
}: {
  jobs: JobListing[];
  selected: ReadonlySet<string>;
}) {
  return (
    <ul className="mt-4 divide-y divide-slate-100">
      {jobs.map((job) => (
        <JobRow
          key={job.id}
          job={job}
          selectable={{
            selected: selected.has(job.id),
            onToggle: () => toggleSelectedJob(job.id),
          }}
        />
      ))}
    </ul>
  );
}
