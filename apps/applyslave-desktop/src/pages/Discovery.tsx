import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { backendClient } from "../services/backend";
import type { JobListing } from "../types/api";

type SortMode = "relevance" | "date" | "company";

export function DiscoveryPage() {
  const queryClient = useQueryClient();
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [selectedJobs, setSelectedJobs] = useState<Set<string>>(new Set());
  const [sortMode, setSortMode] = useState<SortMode>("relevance");

  const suggestionsQuery = useQuery({
    queryKey: ["suggested-searches"],
    queryFn: backendClient.getSuggestedSearches,
  });

  // Set default keywords from suggestions on first load
  useEffect(() => {
    if (suggestionsQuery.data?.suggestions?.length && keywords === "") {
      setKeywords(suggestionsQuery.data.suggestions[0]);
    }
  }, [suggestionsQuery.data, keywords]);

  const startMutation = useMutation({
    mutationFn: backendClient.startDiscovery,
    onSuccess: (response) => {
      setActiveTaskId(response.task_id);
      setSelectedJobs(new Set());
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
      setSelectedJobs(new Set());
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

  const toggleJob = (jobId: string) => {
    setSelectedJobs((previous) => {
      const next = new Set(previous);
      next.has(jobId) ? next.delete(jobId) : next.add(jobId);
      return next;
    });
  };

  const submitSelected = () => {
    const selected = sortedJobs.filter((job) => selectedJobs.has(job.id));
    if (selected.length === 0) return;
    submitMutation.mutate(
      selected.map((job) => ({
        url: job.apply_url ?? job.url,
        company: job.company,
        title: job.title,
      })),
    );
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
                onClick={() => setKeywords(suggestion)}
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
            <span className="text-sm font-medium text-slate-700">
              Keywords
            </span>
            <input
              value={keywords}
              onChange={(event) => setKeywords(event.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">
              Location
            </span>
            <input
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="Seattle, remote, …"
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
            />
          </label>
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={remoteOnly}
            onChange={(event) => setRemoteOnly(event.target.checked)}
          />
          Remote only
        </label>
        <div className="mt-4">
          <button
            type="button"
            onClick={() =>
              startMutation.mutate({
                keywords,
                location,
                remote_only: remoteOnly,
                exclude_companies: [],
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
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-medium">
                Results
                {taskQuery.data?.status && (
                  <span className="ml-2 text-sm font-normal text-slate-500">
                    ({taskQuery.data.status}
                    {sortedJobs.length > 0 && ` · ${sortedJobs.length} jobs`})
                  </span>
                )}
              </h2>
            </div>
            <button
              type="button"
              disabled={selectedJobs.size === 0 || submitMutation.isPending}
              onClick={submitSelected}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-emerald-500 disabled:opacity-50"
            >
              {submitMutation.isPending
                ? "Queueing…"
                : `Queue ${selectedJobs.size} selected`}
            </button>
          </header>

          {sortedJobs.length > 0 && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <span className="text-slate-500">Sort by:</span>
              <SortButton
                active={sortMode === "relevance"}
                onClick={() => setSortMode("relevance")}
              >
                Relevance
              </SortButton>
              <SortButton
                active={sortMode === "date"}
                onClick={() => setSortMode("date")}
              >
                Date posted
              </SortButton>
              <SortButton
                active={sortMode === "company"}
                onClick={() => setSortMode("company")}
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
            <JobList
              jobs={sortedJobs}
              selected={selectedJobs}
              onToggle={toggleJob}
            />
          )}
        </section>
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
  onToggle,
}: {
  jobs: JobListing[];
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <ul className="mt-4 divide-y divide-slate-100">
      {jobs.map((job) => (
        <li key={job.id} className="flex items-start gap-3 py-3">
          <input
            type="checkbox"
            className="mt-1"
            checked={selected.has(job.id)}
            onChange={() => onToggle(job.id)}
          />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{job.title}</span>
              {job.relevance_score != null && (
                <RelevanceBadge score={job.relevance_score} />
              )}
            </div>
            <div className="text-sm text-slate-600">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
              {job.remote ? " · Remote" : ""}
            </div>
            <div className="mt-0.5 flex items-center gap-3 text-xs text-slate-500">
              <a
                href={job.url}
                target="_blank"
                rel="noreferrer"
                className="hover:underline"
              >
                Apply →
              </a>
              {job.posted_at && (
                <span>{formatDate(job.posted_at)}</span>
              )}
              <span className="rounded bg-slate-100 px-1.5 py-0.5 uppercase tracking-wide">
                {job.source}
              </span>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function RelevanceBadge({ score }: { score: number }) {
  let tone = "bg-slate-100 text-slate-600";
  if (score >= 70) tone = "bg-green-100 text-green-700";
  else if (score >= 40) tone = "bg-amber-100 text-amber-700";
  else tone = "bg-slate-100 text-slate-500";

  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>
      {score}%
    </span>
  );
}

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  } catch {
    return isoString;
  }
}
