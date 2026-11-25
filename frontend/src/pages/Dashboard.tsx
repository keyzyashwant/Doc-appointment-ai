import { useEffect, useState } from "react";

type BackendStatus = "checking" | "ok" | "offline";

const PANELS = [
  {
    title: "Call",
    detail: "Voice call controls will appear here.",
  },
  {
    title: "Transcript",
    detail: "The live call transcript will appear here.",
  },
  {
    title: "Doctors",
    detail: "The doctor directory will appear here.",
  },
  {
    title: "Appointments",
    detail: "Booked appointments, identified by phone number, will appear here.",
  },
] as const;

export function Dashboard() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let cancelled = false;

    fetch("/api/health")
      .then((response) => {
        if (!response.ok) {
          throw new Error("Health check failed");
        }
        return response.json() as Promise<{ status?: string }>;
      })
      .then((body) => {
        if (!cancelled) {
          setBackendStatus(body.status === "ok" ? "ok" : "offline");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBackendStatus("offline");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const statusLabel =
    backendStatus === "ok" ? "Backend connected" : backendStatus === "offline" ? "Backend offline" : "Checking backend";

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
        <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-medium tracking-wide text-teal-700">Reception desk</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">Doctor Appointment AI</h1>
          </div>
          <p
            className={`w-fit rounded-full px-3 py-1 text-sm font-medium ${
              backendStatus === "ok"
                ? "bg-teal-100 text-teal-800"
                : backendStatus === "offline"
                  ? "bg-rose-100 text-rose-800"
                  : "bg-slate-200 text-slate-700"
            }`}
          >
            {statusLabel}
          </p>
        </header>

        <section className="grid gap-4 md:grid-cols-2">
          {PANELS.map((panel) => (
            <article key={panel.title} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold">{panel.title}</h2>
              <div className="mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-sm text-slate-600">
                {panel.detail}
              </div>
            </article>
          ))}
        </section>
      </div>
    </main>
  );
}
