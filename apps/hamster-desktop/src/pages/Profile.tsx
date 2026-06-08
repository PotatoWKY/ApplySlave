import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { backendClient } from "../services/backend";
import type { Education, Experience, UserProfile } from "../types/api";

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
  const [dirty, setDirty] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (profileQuery.data) {
      setForm(profileQuery.data);
      setSkillsText(profileQuery.data.skills.join(", "));
      setDirty(false);
    }
  }, [profileQuery.data]);

  const saveMutation = useMutation({
    mutationFn: backendClient.saveProfile,
    onSuccess: (saved) => {
      queryClient.setQueryData(["profile"], saved);
      setDirty(false);
    },
  });

  const resumeMutation = useMutation({
    mutationFn: backendClient.uploadResume,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });

  const hasSavedProfile =
    (profileQuery.data?.first_name ?? "") !== "" ||
    (profileQuery.data?.email ?? "") !== "";

  const updateField = useCallback(
    (field: keyof UserProfile) =>
      (event: ChangeEvent<HTMLInputElement>) => {
        setForm((current) => ({ ...current, [field]: event.target.value }));
        setDirty(true);
      },
    [],
  );

  const updateExperience = (
    index: number,
    field: keyof Experience,
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      experience: current.experience.map((exp, idx) =>
        idx === index ? { ...exp, [field]: value } : exp,
      ),
    }));
    setDirty(true);
  };

  const addExperience = () => {
    setForm((current) => ({
      ...current,
      experience: [
        ...current.experience,
        { company: "", title: "", description: "", start_date: "", end_date: "" },
      ],
    }));
    setDirty(true);
  };

  const removeExperience = (index: number) => {
    setForm((current) => ({
      ...current,
      experience: current.experience.filter((_, idx) => idx !== index),
    }));
    setDirty(true);
  };

  const updateEducation = (
    index: number,
    field: keyof Education,
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      education: current.education.map((edu, idx) =>
        idx === index ? { ...edu, [field]: value } : edu,
      ),
    }));
    setDirty(true);
  };

  const addEducation = () => {
    setForm((current) => ({
      ...current,
      education: [
        ...current.education,
        { school: "", degree: "", major: "", start_date: "", end_date: "" },
      ],
    }));
    setDirty(true);
  };

  const removeEducation = (index: number) => {
    setForm((current) => ({
      ...current,
      education: current.education.filter((_, idx) => idx !== index),
    }));
    setDirty(true);
  };

  const handleResumeUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (
      hasSavedProfile &&
      !window.confirm(
        "Uploading a new resume will overwrite the current profile. Continue?",
      )
    ) {
      event.target.value = "";
      return;
    }
    resumeMutation.mutate(file);
    event.target.value = "";
  };

  const triggerUpload = () => fileInputRef.current?.click();

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
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        onChange={handleResumeUpload}
        disabled={resumeMutation.isPending}
        className="hidden"
      />

      <ProfileSummary
        profile={profileQuery.data}
        onReplaceResume={triggerUpload}
        uploadDisabled={resumeMutation.isPending}
      />

      <ResumeUploadStatus resumeMutation={resumeMutation} />

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
            onChange={(event) => {
              setSkillsText(event.target.value);
              setDirty(true);
            }}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
          />
        </div>
      </section>

      <ExperienceSection
        items={form.experience}
        onChange={updateExperience}
        onAdd={addExperience}
        onRemove={removeExperience}
      />

      <EducationSection
        items={form.education}
        onChange={updateEducation}
        onAdd={addEducation}
        onRemove={removeEducation}
      />

      <SaveBar
        dirty={dirty}
        saving={saveMutation.isPending}
        saved={saveMutation.isSuccess}
        onSave={handleSave}
      />
    </div>
  );
}

// --- Profile summary header ---------------------------------------------

function ProfileSummary({
  profile,
  onReplaceResume,
  uploadDisabled,
}: {
  profile: UserProfile | null | undefined;
  onReplaceResume: () => void;
  uploadDisabled: boolean;
}) {
  const hasProfile =
    profile && (profile.first_name !== "" || profile.email !== "");

  if (!hasProfile) {
    return (
      <section className="rounded-md border border-dashed border-slate-300 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-medium">Get started</h2>
        <p className="mt-1 text-sm text-slate-500">
          Upload a PDF resume and we'll parse it locally to fill in your
          profile. Your data never leaves this machine.
        </p>
        <button
          type="button"
          onClick={onReplaceResume}
          disabled={uploadDisabled}
          className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
        >
          Upload resume
        </button>
      </section>
    );
  }

  const fullName = `${profile.first_name} ${profile.last_name}`.trim();

  return (
    <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-medium">{fullName || "Your profile"}</h2>
          <div className="mt-1 text-sm text-slate-600">{profile.email}</div>
          {profile.location && (
            <div className="text-sm text-slate-500">{profile.location}</div>
          )}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            {profile.phone && <span>{profile.phone}</span>}
            {profile.linkedin_url && (
              <a
                href={profile.linkedin_url}
                target="_blank"
                rel="noreferrer"
                className="hover:underline"
              >
                LinkedIn
              </a>
            )}
            {profile.github_url && (
              <a
                href={profile.github_url}
                target="_blank"
                rel="noreferrer"
                className="hover:underline"
              >
                GitHub
              </a>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={onReplaceResume}
          disabled={uploadDisabled}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Replace resume
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <StatPill label="Experience" value={profile.experience.length} />
        <StatPill label="Education" value={profile.education.length} />
        <StatPill label="Skills" value={profile.skills.length} />
      </div>
    </section>
  );
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <span className="rounded-full bg-slate-100 px-3 py-1 font-medium text-slate-700">
      {value} {label}
    </span>
  );
}

// --- Resume upload status ------------------------------------------------

type ResumeUploadResponse = {
  path: string;
  llm_used: boolean;
  llm_error?: string | null;
  profile: UserProfile | null;
  parsed_fields: Record<string, string | null>;
};

type ResumeMutation = {
  isPending: boolean;
  data: ResumeUploadResponse | undefined;
  error: unknown;
};

function ResumeUploadStatus({
  resumeMutation,
}: {
  resumeMutation: ResumeMutation;
}) {
  if (resumeMutation.isPending) {
    return (
      <div className="rounded-md bg-slate-50 p-4 text-sm">
        <div className="font-medium text-slate-700">
          Parsing your resume with AI…
        </div>
        <div className="mt-1 text-slate-500">
          This takes ~30s the first time (loading the model) and ~10s
          thereafter. Everything runs locally.
        </div>
      </div>
    );
  }

  if (resumeMutation.error) {
    return (
      <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">
        {(resumeMutation.error as Error).message}
      </div>
    );
  }

  if (!resumeMutation.data) return null;

  if (resumeMutation.data.llm_used) {
    return (
      <div className="rounded-md bg-green-50 p-4 text-sm text-green-800">
        <div className="font-medium">Resume processed.</div>
        <div className="mt-1">
          AI extracted{" "}
          <strong>
            {resumeMutation.data.profile?.experience.length ?? 0}
          </strong>{" "}
          experience,{" "}
          <strong>
            {resumeMutation.data.profile?.education.length ?? 0}
          </strong>{" "}
          education, and{" "}
          <strong>
            {resumeMutation.data.profile?.skills.length ?? 0}
          </strong>{" "}
          skills. Review below and edit as needed.
        </div>
      </div>
    );
  }

  if (resumeMutation.data.llm_error) {
    return (
      <div className="rounded-md bg-amber-50 p-4 text-sm text-amber-800">
        <div className="font-medium">AI extraction failed.</div>
        <div className="mt-1">
          Error: <code>{resumeMutation.data.llm_error}</code>
        </div>
        <div className="mt-1">
          Fell back to regex-only extraction of contact info. The rest of
          the profile is unchanged.
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md bg-amber-50 p-4 text-sm text-amber-800">
      The local AI model isn't installed yet, so only basic fields
      (name, email, phone) were extracted.
    </div>
  );
}

// --- Editable experience / education ------------------------------------

function ExperienceSection({
  items,
  onChange,
  onAdd,
  onRemove,
}: {
  items: Experience[];
  onChange: (index: number, field: keyof Experience, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-medium">Experience</h2>
        <button
          type="button"
          onClick={onAdd}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          + Add experience
        </button>
      </div>
      {items.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">
          Nothing extracted yet. Upload a resume or add an entry manually.
        </p>
      )}
      <div className="mt-4 space-y-4">
        {items.map((exp, index) => (
          <div
            key={index}
            className="rounded border border-slate-200 p-4"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="Company"
                value={exp.company}
                onChange={(event) =>
                  onChange(index, "company", event.target.value)
                }
              />
              <Field
                label="Title"
                value={exp.title}
                onChange={(event) =>
                  onChange(index, "title", event.target.value)
                }
              />
              <Field
                label="Start"
                placeholder="2020-07"
                value={exp.start_date ?? ""}
                onChange={(event) =>
                  onChange(index, "start_date", event.target.value)
                }
              />
              <Field
                label="End (leave blank = present)"
                placeholder="2023-05"
                value={exp.end_date ?? ""}
                onChange={(event) =>
                  onChange(index, "end_date", event.target.value)
                }
              />
            </div>
            <div className="mt-3">
              <label className="text-sm font-medium text-slate-700">
                Description
              </label>
              <textarea
                value={exp.description ?? ""}
                onChange={(event) =>
                  onChange(index, "description", event.target.value)
                }
                rows={4}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
              />
            </div>
            <div className="mt-3 text-right">
              <button
                type="button"
                onClick={() => onRemove(index)}
                className="text-xs text-red-600 hover:underline"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function EducationSection({
  items,
  onChange,
  onAdd,
  onRemove,
}: {
  items: Education[];
  onChange: (index: number, field: keyof Education, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-medium">Education</h2>
        <button
          type="button"
          onClick={onAdd}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          + Add education
        </button>
      </div>
      {items.length === 0 && (
        <p className="mt-3 text-sm text-slate-500">
          Nothing extracted yet. Upload a resume or add an entry manually.
        </p>
      )}
      <div className="mt-4 space-y-4">
        {items.map((edu, index) => (
          <div
            key={index}
            className="rounded border border-slate-200 p-4"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="School"
                value={edu.school}
                onChange={(event) =>
                  onChange(index, "school", event.target.value)
                }
              />
              <Field
                label="Degree"
                placeholder="BS, MS, PhD…"
                value={edu.degree ?? ""}
                onChange={(event) =>
                  onChange(index, "degree", event.target.value)
                }
              />
              <Field
                label="Major"
                value={edu.major ?? ""}
                onChange={(event) =>
                  onChange(index, "major", event.target.value)
                }
              />
              <div className="grid grid-cols-2 gap-2">
                <Field
                  label="Start"
                  placeholder="2016-09"
                  value={edu.start_date ?? ""}
                  onChange={(event) =>
                    onChange(index, "start_date", event.target.value)
                  }
                />
                <Field
                  label="End"
                  placeholder="2020-06"
                  value={edu.end_date ?? ""}
                  onChange={(event) =>
                    onChange(index, "end_date", event.target.value)
                  }
                />
              </div>
            </div>
            <div className="mt-3 text-right">
              <button
                type="button"
                onClick={() => onRemove(index)}
                className="text-xs text-red-600 hover:underline"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// --- Sticky save bar ----------------------------------------------------

function SaveBar({
  dirty,
  saving,
  saved,
  onSave,
}: {
  dirty: boolean;
  saving: boolean;
  saved: boolean;
  onSave: () => void;
}) {
  return (
    <div className="sticky bottom-0 -mx-6 border-t border-slate-200 bg-white px-6 py-3 shadow-[0_-4px_12px_-8px_rgb(0_0_0_/_0.15)]">
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">
          {dirty ? "You have unsaved changes." : saved ? "All changes saved." : "No changes."}
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={saving || !dirty}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save profile"}
        </button>
      </div>
    </div>
  );
}

// --- Primitives ---------------------------------------------------------

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
      />
    </label>
  );
}
