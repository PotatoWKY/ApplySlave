import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, useEffect, useState } from "react";

import { backendClient } from "../services/backend";
import type { UserProfile } from "../types/api";

const EMPTY_PROFILE: UserProfile = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  location: "",
  linkedin_url: "",
  github_url: "",
  education: [],
  experience: [],
  skills: [],
  resume_path: null,
};

export function ProfilePage() {
  const queryClient = useQueryClient();
  const profileQuery = useQuery({
    queryKey: ["profile"],
    queryFn: backendClient.getProfile,
  });

  const [form, setForm] = useState<UserProfile>(EMPTY_PROFILE);
  const [skillsText, setSkillsText] = useState("");

  useEffect(() => {
    if (profileQuery.data) {
      setForm(profileQuery.data);
      setSkillsText(profileQuery.data.skills.join(", "));
    }
  }, [profileQuery.data]);

  const saveMutation = useMutation({
    mutationFn: backendClient.saveProfile,
    onSuccess: (saved) => {
      queryClient.setQueryData(["profile"], saved);
    },
  });

  const resumeMutation = useMutation({
    mutationFn: backendClient.uploadResume,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const updateField = (field: keyof UserProfile) =>
    (event: ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [field]: event.target.value }));

  const handleResumeUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    resumeMutation.mutate(file);
  };

  const handleSave = () => {
    const skills = skillsText
      .split(",")
      .map((skill) => skill.trim())
      .filter(Boolean);
    saveMutation.mutate({ ...form, skills });
  };

  if (profileQuery.isLoading) {
    return <div className="text-slate-500">Loading profile…</div>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-medium">Upload your resume</h2>
        <p className="mt-1 text-sm text-slate-500">
          We'll parse the PDF to auto-fill the fields below. Nothing leaves
          your machine.
        </p>
        <input
          type="file"
          accept="application/pdf"
          onChange={handleResumeUpload}
          disabled={resumeMutation.isPending}
          className="mt-4 block"
        />
        {resumeMutation.isPending && (
          <p className="mt-2 text-sm text-slate-500">Parsing…</p>
        )}
        {resumeMutation.data && (
          <p className="mt-2 text-sm text-green-600">
            Uploaded to {resumeMutation.data.path}
          </p>
        )}
        {resumeMutation.error && (
          <p className="mt-2 text-sm text-red-500">
            {(resumeMutation.error as Error).message}
          </p>
        )}
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-medium">Basic info</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field
            label="First name"
            value={form.first_name}
            onChange={updateField("first_name")}
          />
          <Field
            label="Last name"
            value={form.last_name}
            onChange={updateField("last_name")}
          />
          <Field
            label="Email"
            type="email"
            value={form.email}
            onChange={updateField("email")}
          />
          <Field
            label="Phone"
            value={form.phone ?? ""}
            onChange={updateField("phone")}
          />
          <Field
            label="Location"
            value={form.location ?? ""}
            onChange={updateField("location")}
          />
          <Field
            label="LinkedIn URL"
            value={form.linkedin_url ?? ""}
            onChange={updateField("linkedin_url")}
          />
          <Field
            label="GitHub URL"
            value={form.github_url ?? ""}
            onChange={updateField("github_url")}
          />
        </div>
        <div className="mt-4">
          <label className="text-sm font-medium text-slate-700">
            Skills (comma separated)
          </label>
          <input
            type="text"
            value={skillsText}
            onChange={(event) => setSkillsText(event.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="mt-6 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
        >
          {saveMutation.isPending ? "Saving…" : "Save profile"}
        </button>
        {saveMutation.isSuccess && (
          <span className="ml-3 text-sm text-green-600">Saved.</span>
        )}
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={onChange}
        className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
      />
    </label>
  );
}
