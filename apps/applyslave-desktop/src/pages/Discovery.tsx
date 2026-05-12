import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { backendClient } from "../services/backend";
import type { JobListing } from "../types/api";

export function DiscoveryPage() {
  const queryClient = useQueryClient();
  const [keywords, setKeywords] = useState("software engineer");
  const [location, setLocation] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [selectedJobs, setSelectedJobs] = useState<Set<string>>(new Set());

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

  const jobs = taskQuery.data?.results ?? [];

  useEffect(() => {
    if (!taskQuery.data) return;
    if (taskQuery.data.status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    }
  }, [taskQuery.data, queryClient]);

  const toggleJob = (jobId: string) => {
    setSelectedJobs((previous) => {
      const next = new Set(previous);
      next.has(jobId) ? next.delete(jobId) : next.add(jobId);
      return next;
    });
  };

  const submitSelected = () => {
    const selected = jobs.filter((job) => selectedJobs.has(job.id));
    if (selected.length === 0) return;
    submitMutation.mutate(
      selected.map((job) => ({
        url: job.apply_url ?? job.url,
        company: job.company,
        title: job.title,
      })),
    );
  };

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-medium">Search public ATS boards</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <label className="block sm:col-span-2">
            <span className="text-sm font-medium text-slate-700">
              Keywords
            </span>
            <input
              value={keywords}
              onChange={(event) => setKeywords(event.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">
              Location
            </span>
            <input
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="remote, san francisco, …"
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm"
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
            disabled={startMutation.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
          >
            {startMutation.isPending ? "Searching…" : "Search"}
          </button>
        </div>
      </section>

      {activeTaskId && (
        <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
          <header className="flex items-center justify-between">
            <h2 className="text-xl font-medium">
              Results
              {taskQuery.data?.status && (
                <span className="ml-3 text-sm font-normal text-slate-500">
                  ({taskQuery.data.status})
                </span>
              )}
            </h2>
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

          {jobs.length === 0 && taskQuery.data?.status === "completed" ? (
            <p className="mt-3 text-sm text-slate-500">
              No jobs matched the query.
            </p>
          ) : (
            <JobList
              jobs={jobs}
              selected={selectedJobs}
              onToggle={toggleJob}
            />
          )}
        </section>
      )}
    </div>
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
            <div className="font-medium">{job.title}</div>
            <div className="text-sm text-slate-600">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
              {job.remote ? " · Remote" : ""}
            </div>
            <a
              href={job.url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-slate-500 hover:underline"
            >
              {job.url}
            </a>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs uppercase tracking-wide text-slate-600">
            {job.source}
          </span>
        </li>
      ))}
    </ul>
  );
}
