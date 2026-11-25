import { useEffect, useState } from "react";
import type { Appointment, LiveEvent } from "../types";

type AppointmentTableProps = {
  event: LiveEvent | null;
};

function formatAppointmentTime(start: string | null, end: string | null): string {
  if (!start) return "—";
  const startLabel = new Date(start).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
  return end
    ? `${startLabel} – ${new Date(end).toLocaleTimeString(undefined, { timeStyle: "short" })}`
    : startLabel;
}

export function AppointmentTable({ event }: AppointmentTableProps) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highlightedAppointmentId, setHighlightedAppointmentId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    fetch("/api/appointments", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Could not load appointments (${response.status}).`);
        return (await response.json()) as Appointment[];
      })
      .then((data) => {
        setAppointments(data);
        setError(null);
      })
      .catch((fetchError: unknown) => {
        if (!controller.signal.aborted) {
          setError(fetchError instanceof Error ? fetchError.message : "Could not load appointments.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [event]);

  useEffect(() => {
    const appointmentId = event?.data.appointment_id;
    if (typeof appointmentId !== "number") return;

    setHighlightedAppointmentId(appointmentId);
    const timer = window.setTimeout(() => setHighlightedAppointmentId(null), 2500);
    return () => window.clearTimeout(timer);
  }, [event]);

  return (
    <section className="rounded border border-slate-300 bg-white p-4" aria-labelledby="appointments-heading">
      <h2 id="appointments-heading" className="mb-4 text-lg font-semibold">Appointments</h2>
      {loading && <p className="text-sm text-slate-500">Loading appointments…</p>}
      {error && <p className="mb-3 text-sm text-rose-700" role="alert">{error}</p>}
      {!loading && !error && appointments.length === 0 && (
        <p className="text-sm text-slate-500">No appointments found.</p>
      )}
      {!loading && !error && appointments.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-300 text-slate-600">
                <th className="px-2 py-2 font-medium">Phone</th>
                <th className="px-2 py-2 font-medium">Doctor</th>
                <th className="px-2 py-2 font-medium">Time</th>
                <th className="px-2 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {appointments.map((appointment) => (
                <tr
                  className={`border-b border-slate-200 ${
                    highlightedAppointmentId === appointment.id ? "bg-amber-100" : ""
                  }`}
                  key={appointment.id}
                >
                  <td className="px-2 py-2 font-mono">{appointment.patient_phone}</td>
                  <td className="px-2 py-2">{appointment.doctor_name}</td>
                  <td className="px-2 py-2">{formatAppointmentTime(appointment.slot_start, appointment.slot_end)}</td>
                  <td className="px-2 py-2 capitalize">{appointment.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}