import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { ApplicationsPage } from "./pages/Applications";
import { DiscoveryPage } from "./pages/Discovery";
import { ProfilePage } from "./pages/Profile";
import { SettingsPage } from "./pages/Settings";
import { backendClient } from "./services/backend";
import type { UserProfile } from "./types/api";

function BackendStatusPill() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: backendClient.getHealth,
    refetchInterval: 10_000,
    retry: 3,
  });
  if (isLoading) {
    return <Pill tone="slate">connecting…</Pill>;
  }
  if (error) {
    return <Pill tone="red">backend offline</Pill>;
  }
  return (
    <Pill tone={data?.model_installed ? "green" : "amber"}>
      backend {data?.status}
      {data?.model_installed ? " • model ready" : " • model missing"}
    </Pill>
  );
}

function Pill({
  tone,
  children,
}: {
  tone: "slate" | "red" | "green" | "amber";
  children: React.ReactNode;
}) {
  const classes: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700",
    red: "bg-red-100 text-red-700",
    green: "bg-green-100 text-green-700",
    amber: "bg-amber-100 text-amber-700",
  };
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ${classes[tone]}`}>
      {children}
    </span>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="w-60 border-r border-slate-200 bg-white p-4">
        <div className="mb-6">
          <h1 className="text-lg font-semibold">Hamster</h1>
          <p className="mt-1 text-xs text-slate-500">Auto-apply, locally</p>
        </div>
        <nav className="space-y-1 text-sm">
          <NavItem to="/profile">Profile</NavItem>
          <NavItem to="/discover">Discover jobs</NavItem>
          <NavItem to="/applications">Applications</NavItem>
          <NavItem to="/settings">Settings</NavItem>
        </nav>
      </aside>
      <main className="flex-1">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
          <span className="text-sm text-slate-500">Local desktop build</span>
          <BackendStatusPill />
        </header>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `block rounded-md px-3 py-2 transition ${
          isActive
            ? "bg-slate-100 font-medium text-slate-900"
            : "text-slate-600 hover:bg-slate-50"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

function RootRedirect() {
  const { data, isLoading } = useQuery({
    queryKey: ["profile"],
    queryFn: backendClient.getProfile,
  });

  if (isLoading) {
    return (
      <div className="py-10 text-center text-sm text-slate-500">
        Checking profile…
      </div>
    );
  }

  const hasProfile = profileLooksComplete(data);
  return <Navigate to={hasProfile ? "/discover" : "/profile"} replace />;
}

function profileLooksComplete(profile: UserProfile | null | undefined): boolean {
  if (!profile) return false;
  return Boolean(profile.first_name && profile.email);
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/discover" element={<DiscoveryPage />} />
          <Route path="/applications" element={<ApplicationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
