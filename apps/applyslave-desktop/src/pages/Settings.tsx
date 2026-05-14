import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { backendClient, openWebSocket } from "../services/backend";

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <ModelSection />
    </div>
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
