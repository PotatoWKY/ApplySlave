import { useQuery } from "@tanstack/react-query";

const BACKEND_URL = "http://localhost:8765";

type HealthResponse = {
  status: string;
  version: string;
};

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${BACKEND_URL}/api/health`);
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`);
  }
  return response.json();
}

function BackendStatus() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    retry: 3,
    retryDelay: 500,
  });

  if (isLoading) {
    return <span className="text-slate-500">Connecting to backend…</span>;
  }
  if (error) {
    return (
      <span className="text-red-500">
        Backend unreachable: {(error as Error).message}
      </span>
    );
  }
  return (
    <span className="text-green-600">
      Backend {data?.status} (v{data?.version})
    </span>
  );
}

function App() {
  return (
    <main className="min-h-screen bg-slate-50 p-8 text-slate-900">
      <h1 className="text-3xl font-semibold">ApplySlave</h1>
      <p className="mt-2 text-slate-600">
        Local-first resume auto-apply tool. Desktop scaffold is running.
      </p>
      <div className="mt-6 rounded-md border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-2 text-lg font-medium">Backend status</h2>
        <BackendStatus />
      </div>
    </main>
  );
}

export default App;
