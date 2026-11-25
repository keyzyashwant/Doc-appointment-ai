import { useEffect, useState } from "react";
import type { Doctor, LiveEvent } from "../types";

type DoctorListProps = {
  event: LiveEvent | null;
};

function formatSlot(date: string): string {
  return new Date(date).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function DoctorList({ event }: DoctorListProps) {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highlightedSlotId, setHighlightedSlotId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);

    fetch("/api/doctors", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Could not load doctors (${response.status}).`);
        return (await response.json()) as Doctor[];
      })
      .then((data) => {
        setDoctors(data);
        setError(null);
      })
      .catch((fetchError: unknown) => {
        if (!controller.signal.aborted) {
          setError(fetchError instanceof Error ? fetchError.message : "Could not load doctors.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [event]);

  useEffect(() => {
    const slotId = event?.data.slot_id;
    if (typeof slotId !== "number") return;

    setHighlightedSlotId(slotId);
    const timer = window.setTimeout(() => setHighlightedSlotId(null), 2500);
    return () => window.clearTimeout(timer);
  }, [event]);

  return (
    <section className="rounded border border-slate-300 bg-white p-4" aria-labelledby="doctors-heading">
      <h2 id="doctors-heading" className="mb-4 text-lg font-semibold">Doctors and availability</h2>
      {loading && <p className="text-sm text-slate-500">Loading doctors…</p>}
      {error && <p className="mb-3 text-sm text-rose-700" role="alert">{error}</p>}
      {!loading && !error && doctors.length === 0 && (
        <p className="text-sm text-slate-500">No doctors found.</p>
      )}
      <ul className="divide-y divide-slate-200">
        {doctors.map((doctor) => (
          <li className="py-3 first:pt-0 last:pb-0" key={doctor.id}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h3 className="font-medium">{doctor.name}</h3>
              <span className="text-sm text-slate-600">{doctor.speciality}</span>
            </div>
            {doctor.available_slots.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No upcoming slots.</p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-2" aria-label={`Available slots for ${doctor.name}`}>
                {doctor.available_slots.slice(0, 3).map((slot) => (
                  <li
                    className={`rounded border px-2 py-1 text-xs ${
                      highlightedSlotId === slot.id
                        ? "border-amber-500 bg-amber-100"
                        : "border-slate-300 bg-slate-50"
                    }`}
                    key={slot.id}
                  >
                    {formatSlot(slot.start_time)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}