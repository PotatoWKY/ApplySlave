import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { JobRow } from "../components/JobRow";
import { backendClient } from "../services/backend";
import type { ApplicationRecord, JobListing } from "../types/api";

export function ApplicationsPage() {
  const applicationsQuery = useQuery({
    queryKey: ["applications"],
    queryFn: () => backendClient.listApplications(),
    refetchInterval: 5000,
  });

  const applications = applicationsQuery.data?.applications ?? [];

  return (
    <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-medium">Applications</h2>
      <AddByUrl />
      {applicationsQuery.isLoading ? (
        <p className="mt-3 text-sm text-slate-500">Loading…</p>
      ) : applications.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          No applications yet. Queue some jobs from the Discovery page.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-slate-100">
          {applications.map((record) => (
            <JobRow
              key={record.id ?? record.url}
              job={recordToJob(record)}
              status={record.status}
              error={record.error}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Paste an application URL to queue it directly. Goes into the same queue as
 * jobs sent from Discovery — the worker doesn't care where a row came from.
 */
function AddByUrl() {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const submitMutation = useMutation({
    mutationFn: (value: string) => backendClient.submitUrl(value),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      if (response.accepted) {
        setUrl("");
        setNotice("Queued.");
      } else {
        setNotice(`Not queued: ${response.reason ?? "already in queue"}.`);
      }
      setTimeout(() => setNotice(null), 2500);
    },
  });

  const trimmed = url.trim();

  return (
    <div className="mt-3">
      <div className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(event) => {
            setUrl(event.target.value);
            setNotice(null);
          }}
          placeholder="Paste an application URL to queue it…"
          className="block flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => submitMutation.mutate(trimmed)}
          disabled={submitMutation.isPending || trimmed === ""}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
        >
          {submitMutation.isPending ? "Queueing…" : "Add"}
        </button>
      </div>
      {notice && <div className="mt-2 text-sm text-slate-600">{notice}</div>}
      {submitMutation.isError && (
        <div className="mt-2 text-sm text-red-600">
          {(submitMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}

/**
 * Build a JobListing-shaped object for a row whose source data lives on the
 * application record. Records queued before we started capturing the full
 * JobListing on submit only have url/company/title — we fill the rest with
 * sensible defaults so JobRow still renders cleanly.
 */
function recordToJob(record: ApplicationRecord): JobListing {
  if (record.job) {
    return record.job;
  }
  return {
    id: String(record.id ?? record.url),
    source: "linkedin",
    company: record.company,
    title: record.title,
    url: record.url,
    apply_url: record.url,
    remote: false,
  };
}
