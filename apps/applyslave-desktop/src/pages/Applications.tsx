import { useQuery } from "@tanstack/react-query";

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
