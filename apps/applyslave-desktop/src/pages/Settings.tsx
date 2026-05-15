import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { backendClient, openWebSocket } from "../services/backend";

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <DryRunSection />
      <JSearchSection />
      <ModelSection />
    </div>
  );
}

function DryRunSection() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: backendClient.getSettings,
  });

  const updateMutation = useMutation({
    mutationFn: (dryRun: boolean) =>
      backendClient.saveSettings({ dry_run: dryRun ? "true" : "" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  // Default: dry_run is on if not explicitly set
  const stored = settingsQuery.data?.dry_run;
  const isOn = stored === undefined ? true : Boolean(stored);

  return (
    <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-medium">Dry-run mode</h2>
          <p className="mt-1 text-sm text-slate-500">
            When ON, the apply pipeline opens each posting, fills the form,
            and takes a screenshot — but stops just before clicking Submit.
            Use this until you're confident the LLM picks the right values.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Screenshots saved to ~/Library/Application Support/ApplySlave/screenshots/
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={isOn}
          onClick={() => updateMutation.mutate(!isOn)}
          disabled={updateMutation.isPending}
          className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition ${
            isOn ? "bg-slate-900" : "bg-slate-300"
          } disabled:opacity-50`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
              isOn ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
      </div>
      {!isOn && (
        <div className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-700">
          <strong>Live submission is enabled.</strong> The next queued
          application will be actually submitted to the employer.
        </div>
      )}
    </section>
  );
}

function JSearchSection() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: backendClient.getSettings,
  });

  const [keyInput, setKeyInput] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settingsQuery.data?.jsearch_api_key) {
      setKeyInput(settingsQuery.data.jsearch_api_key as string);
    }
  }, [settingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: (key: string) =>
      backendClient.saveSettings({ jsearch_api_key: key || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
  });

  const maskedKey = settingsQuery.data?.jsearch_api_key_masked as
    | string
    | undefined;
  const hasKey = Boolean(settingsQuery.data?.jsearch_api_key);

  return (
    <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-medium">Job Search API</h2>
      <p className="mt-1 text-sm text-slate-500">
        Enables searching across all job boards (LinkedIn, Indeed, Glassdoor,
        Workday, etc). Without this, only the 603 tech companies in our local
        list are searched.
      </p>

      <div className="mt-4">
        <label className="block text-sm font-medium text-slate-700">
          JSearch API Key (RapidAPI)
        </label>
        <div className="mt-1 flex gap-2">
          <input
            type="password"
            value={keyInput}
            onChange={(event) => {
              setKeyInput(event.target.value);
              setSaved(false);
            }}
            placeholder="Paste your x-rapidapi-key here"
            className="block flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => saveMutation.mutate(keyInput)}
            disabled={saveMutation.isPending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
          >
            {saveMutation.isPending ? "Saving…" : "Save"}
          </button>
        </div>
        {saved && (
          <div className="mt-2 text-sm text-green-600">Key saved.</div>
        )}
        {hasKey && !saved && (
          <div className="mt-2 text-xs text-slate-500">
            Current key: {maskedKey}
          </div>
        )}
        <div className="mt-3 text-xs text-slate-400">
          Get a free key (200 searches/month) at{" "}
          <a
            href="https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"
            target="_blank"
            rel="noreferrer"
            className="text-slate-600 underline"
          >
            rapidapi.com/jsearch
          </a>
        </div>
      </div>
    </section>
  );
}

function ModelSection() {
  const queryClient = useQueryClient();
  const statusQuery = useQuery({
    queryKey: ["model-status"],
    queryFn: backendClient.getModelStatus,
    refetchInterval: 3000,
  });

  const downloadMutation = useMutation({
    mutationFn: backendClient.startModelDownload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["model-status"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: backendClient.deleteModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["model-status"] });
      queryClient.invalidateQueries({ queryKey: ["health"] });
      setProgress(null);
    },
  });

  const [progress, setProgress] = useState<{
    downloaded: number;
    total: number | null;
  } | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    openWebSocket((event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "model_download_progress") {
          setProgress({
            downloaded: message.downloaded_bytes,
            total: message.total_bytes,
          });
        }
        if (message.type === "model_download_completed") {
          setProgress(null);
          queryClient.invalidateQueries({ queryKey: ["model-status"] });
          queryClient.invalidateQueries({ queryKey: ["health"] });
        }
        if (message.type === "model_download_failed") {
          setProgress(null);
        }
      } catch {
        // ignore non-JSON messages
      }
    }).then((ws) => {
      wsRef.current = ws;
    });
    return () => {
      wsRef.current?.close();
    };
  }, [queryClient]);

  const modelStatus = statusQuery.data;
  const isInstalled = modelStatus?.installed ?? false;
  const isDownloading = modelStatus?.downloading ?? false;
  const modelName = modelStatus?.model_name ?? "unknown";

  const handleDownload = () => {
    downloadMutation.mutate();
  };

  const handleDelete = () => {
    if (
      !window.confirm(
        "Delete the AI model? This frees ~2.3 GB of disk space. " +
          "You can re-download it anytime.",
      )
    ) {
      return;
    }
    deleteMutation.mutate();
  };

  return (
    <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-xl font-medium">AI Model</h2>
      <p className="mt-1 text-sm text-slate-500">
        Used for resume parsing and form filling. Runs entirely on your
        machine (Apple Metal GPU).
      </p>

      <div className="mt-4 rounded-md border border-slate-100 bg-slate-50 p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-slate-700">
              {modelName}
            </div>
            <div className="mt-0.5 text-xs text-slate-500">
              Qwen3 4B Instruct • Q4_K_M quantization • ~2.3 GB
            </div>
          </div>
          <StatusBadge installed={isInstalled} downloading={isDownloading} />
        </div>

        {progress && (
          <ProgressBar
            downloaded={progress.downloaded}
            total={progress.total}
          />
        )}

        <div className="mt-4 flex gap-3">
          {!isInstalled && !isDownloading && (
            <button
              type="button"
              onClick={handleDownload}
              disabled={downloadMutation.isPending}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
            >
              Download model
            </button>
          )}

          {isDownloading && (
            <button
              type="button"
              disabled
              className="rounded-md bg-slate-200 px-4 py-2 text-sm font-medium text-slate-500"
            >
              Downloading…
            </button>
          )}

          {isInstalled && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="rounded-md border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              {deleteMutation.isPending ? "Deleting…" : "Delete model"}
            </button>
          )}

          <button
            type="button"
            onClick={() => statusQuery.refetch()}
            disabled={statusQuery.isFetching}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {statusQuery.isFetching ? "Checking…" : "Check status"}
          </button>
        </div>

        {deleteMutation.isError && (
          <div className="mt-3 text-sm text-red-600">
            Failed to delete: {(deleteMutation.error as Error).message}
          </div>
        )}
        {downloadMutation.isError && (
          <div className="mt-3 text-sm text-red-600">
            Failed to start download:{" "}
            {(downloadMutation.error as Error).message}
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center gap-3 text-xs text-slate-400">
        <span>Model stored at ~/Library/Application Support/ApplySlave/models/</span>
        {statusQuery.dataUpdatedAt > 0 && (
          <span className="ml-auto">
            Last checked: {new Date(statusQuery.dataUpdatedAt).toLocaleTimeString()}
          </span>
        )}
      </div>
    </section>
  );
}

function StatusBadge({
  installed,
  downloading,
}: {
  installed: boolean;
  downloading: boolean;
}) {
  if (downloading) {
    return (
      <span className="rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-700">
        downloading
      </span>
    );
  }
  if (installed) {
    return (
      <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-700">
        installed
      </span>
    );
  }
  return (
    <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">
      not installed
    </span>
  );
}

function ProgressBar({
  downloaded,
  total,
}: {
  downloaded: number;
  total: number | null;
}) {
  const downloadedMB = (downloaded / 1024 / 1024).toFixed(0);
  const totalMB = total ? (total / 1024 / 1024).toFixed(0) : "?";
  const percent = total ? Math.round((downloaded / total) * 100) : null;

  return (
    <div className="mt-3">
      <div className="flex items-center justify-between text-xs text-slate-600">
        <span>
          {downloadedMB} MB / {totalMB} MB
        </span>
        {percent !== null && <span>{percent}%</span>}
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full rounded-full bg-slate-700 transition-all duration-300"
          style={{ width: percent !== null ? `${percent}%` : "30%" }}
        />
      </div>
    </div>
  );
}
