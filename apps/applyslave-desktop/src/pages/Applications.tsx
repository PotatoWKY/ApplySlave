import { useQuery } from "@tanstack/react-query";

import { backendClient } from "../services/backend";
import type { ApplicationRecord, ApplicationStatus } from "../types/api";

const STATUS_COLORS: Record<ApplicationStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  in_progress: "bg-blue-100 text-blue-700",
  submitted: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  skipped: "bg-slate-100 text-slate-500",
  needs_review: "bg-amber-100 text-amber-700",
};

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
            <ApplicationRow key={record.id ?? record.url} record={record} />
          ))}
        </ul>
      )}
    </section>
  );
}

function ApplicationRow({ record }: { record: ApplicationRecord }) {
  const badgeClass = STATUS_COLORS[record.status];
  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="flex-1">
        <div className="font-medium">{record.title}</div>
        <div className="text-sm text-slate-600">{record.company}</div>
        <a
          href={record.url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-slate-500 hover:underline"
        >
          {record.url}
        </a>
        {record.error && (
          <div className="mt-1 text-xs text-red-600">{record.error}</div>
        )}
      </div>
      <span
        className={`rounded-full px-2 py-0.5 text-xs uppercase tracking-wide ${badgeClass}`}
      >
        {record.status.replace("_", " ")}
      </span>
    </li>
  );
}
