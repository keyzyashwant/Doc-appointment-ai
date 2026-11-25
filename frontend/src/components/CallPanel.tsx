import type { VoiceCallStatus } from "../hooks/useVoiceCall";

type CallPanelProps = {
  status: VoiceCallStatus;
  muted: boolean;
  durationSeconds: number;
  error: string | null;
  onStart: () => Promise<void>;
  onEnd: () => Promise<void>;
  onToggleMute: () => void;
};

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
}

export function CallPanel({
  status,
  muted,
  durationSeconds,
  error,
  onStart,
  onEnd,
  onToggleMute,
}: CallPanelProps) {
  const active = status === "connected" || status === "connecting";
  const canStart = !active;
  const statusLabel = status === "error" ? "Call failed" : status;

  return (
    <section className="space-y-4 rounded border border-slate-300 bg-white p-4" aria-labelledby="call-heading">
      <div className="flex items-center justify-between gap-4">
        <h2 id="call-heading" className="text-lg font-semibold">Voice call</h2>
        <span className="text-sm capitalize text-slate-600">{statusLabel}</span>
      </div>

      <p className="font-mono text-2xl tabular-nums" aria-label="Call duration">
        {formatDuration(durationSeconds)}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="rounded border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          type="button"
          onClick={() => void onStart()}
          disabled={!canStart}
        >
          {status === "connecting" ? "Connecting…" : "Start call"}
        </button>
        <button
          className="rounded border border-slate-400 px-4 py-2 text-sm font-medium text-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          type="button"
          onClick={() => void onEnd()}
          disabled={!active}
        >
          End call
        </button>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={muted}
            onChange={onToggleMute}
            disabled={status !== "connected"}
          />
          Mute microphone
        </label>
      </div>

      {error && (
        <p className="rounded border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}