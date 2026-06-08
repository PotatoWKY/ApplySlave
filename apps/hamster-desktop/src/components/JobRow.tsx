/**
 * Shared row renderer for a JobListing.
 *
 * Used by both the Discovery results list and the Applications page so
 * the user sees consistent metadata (salary, level, employment type, source,
 * relevance, posted date) wherever a job appears.
 */

import type { ApplicationStatus, JobListing } from "../types/api";

type Props = {
  job: JobListing;
  /** Optional checkbox state — only used in the Discovery list. */
  selectable?: {
    selected: boolean;
    onToggle: () => void;
  };
  /** Optional application status — shown as a badge in the Applications list. */
  status?: ApplicationStatus;
  /** Optional error message (failed applications). */
  error?: string | null;
};

export function JobRow({ job, selectable, status, error }: Props) {
  const applyUrl = job.apply_url ?? job.url;
  return (
    <li className="flex items-start gap-3 py-4">
      {selectable && (
        <input
          type="checkbox"
          className="mt-1.5"
          checked={selectable.selected}
          onChange={selectable.onToggle}
        />
      )}
      <div className="flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={job.url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-slate-900 hover:text-slate-700 hover:underline"
              >
                {job.title}
              </a>
              {status && <StatusBadge status={status} />}
              {job.relevance_score != null && (
                <RelevanceBadge score={job.relevance_score} />
              )}
              {job.experience_level && (
                <LevelBadge level={job.experience_level} />
              )}
              {job.employment_type && job.employment_type !== "FULLTIME" && (
                <TypeBadge type={job.employment_type} />
              )}
            </div>
            <div className="mt-1 text-sm text-slate-600">
              <span className="font-medium">{job.company}</span>
              {job.location ? ` · ${job.location}` : ""}
              {job.remote ? " · Remote" : ""}
            </div>
            {(job.salary_min != null || job.salary_max != null) && (
              <div className="mt-1 text-sm text-slate-700">
                {formatSalary(job)}
              </div>
            )}
            {error && (
              <div className="mt-1 text-xs text-red-600">{error}</div>
            )}
          </div>
          <a
            href={applyUrl}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Apply →
          </a>
        </div>
        <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
          {job.posted_at && <span>{formatDate(job.posted_at)}</span>}
          <span className="rounded bg-slate-100 px-1.5 py-0.5 uppercase tracking-wide text-slate-600">
            {job.source}
          </span>
        </div>
      </div>
    </li>
  );
}

const STATUS_CLASSES: Record<ApplicationStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  in_progress: "bg-blue-100 text-blue-700",
  submitted: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  skipped: "bg-slate-100 text-slate-500",
  needs_review: "bg-amber-100 text-amber-700",
};

function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${STATUS_CLASSES[status]}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

function RelevanceBadge({ score }: { score: number }) {
  let tone = "bg-slate-100 text-slate-500";
  if (score >= 70) tone = "bg-green-100 text-green-700";
  else if (score >= 40) tone = "bg-amber-100 text-amber-700";

  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>
      {score}% match
    </span>
  );
}

function LevelBadge({ level }: { level: string }) {
  const labels: Record<string, string> = {
    intern: "Intern",
    entry: "Entry",
    mid: "Mid",
    senior: "Senior",
    lead: "Lead+",
  };
  return (
    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
      {labels[level] ?? level}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const labels: Record<string, string> = {
    PARTTIME: "Part-time",
    CONTRACT: "Contract",
    INTERN: "Internship",
  };
  return (
    <span className="rounded-full bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
      {labels[type] ?? type}
    </span>
  );
}

function formatSalary(job: JobListing): string {
  const currency = job.salary_currency ?? "USD";
  const period = job.salary_period ?? "year";
  const periodLabel =
    period === "hour" ? "/hr" : period === "month" ? "/mo" : "/yr";

  const format = (amount: number) => {
    if (amount >= 1000) {
      return `$${(amount / 1000).toFixed(0)}k`;
    }
    return `$${amount.toFixed(0)}`;
  };

  if (job.salary_min != null && job.salary_max != null) {
    if (job.salary_min === job.salary_max) {
      return `${format(job.salary_min)} ${currency}${periodLabel}`;
    }
    return `${format(job.salary_min)} – ${format(job.salary_max)} ${currency}${periodLabel}`;
  }
  if (job.salary_min != null) {
    return `${format(job.salary_min)}+ ${currency}${periodLabel}`;
  }
  if (job.salary_max != null) {
    return `Up to ${format(job.salary_max)} ${currency}${periodLabel}`;
  }
  return "";
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
