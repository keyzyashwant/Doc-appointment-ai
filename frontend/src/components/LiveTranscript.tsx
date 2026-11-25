import { useEffect, useRef } from "react";
import type { TranscriptEntry } from "../types";

type LiveTranscriptProps = {
  entries: TranscriptEntry[];
};

export function LiveTranscript({ entries }: LiveTranscriptProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [entries]);

  return (
    <section className="rounded border border-slate-300 bg-white p-4" aria-labelledby="transcript-heading">
      <h2 id="transcript-heading" className="mb-4 text-lg font-semibold">Live transcript</h2>
      <div className="max-h-80 space-y-3 overflow-y-auto" aria-live="polite" aria-relevant="additions text">
        {entries.length === 0 ? (
          <p className="text-sm text-slate-500">Transcript will appear when the call starts.</p>
        ) : (
          entries.map((entry) => (
            <div
              className={`max-w-[85%] rounded border p-3 text-sm ${
                entry.role === "user"
                  ? "ml-auto border-sky-200 bg-sky-50"
                  : "border-slate-200 bg-slate-50"
              }`}
              key={entry.id}
            >
              <p className="mb-1 text-xs font-medium text-slate-500">
                {entry.role === "user" ? "You" : "Receptionist"}
                {!entry.final && " · listening"}
              </p>
              <p className="whitespace-pre-wrap">{entry.text}</p>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}