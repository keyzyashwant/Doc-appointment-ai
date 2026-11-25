import { AppointmentTable } from "../components/AppointmentTable";
import { CallPanel } from "../components/CallPanel";
import { DoctorList } from "../components/DoctorList";
import { LiveTranscript } from "../components/LiveTranscript";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { useVoiceCall } from "../hooks/useVoiceCall";

export function Dashboard() {
  const call = useVoiceCall();
  const liveEvents = useLiveEvents();

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900">
      <audio ref={call.remoteAudioRef} autoPlay playsInline className="hidden" />
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-slate-600">Reception desk</p>
            <h1 className="mt-1 text-2xl font-semibold">Doctor Appointment AI</h1>
          </div>
          <p className="text-sm text-slate-600" role="status">
            Events: {liveEvents.status}
          </p>
        </header>

        <section className="grid gap-4 lg:grid-cols-2">
          <CallPanel
            status={call.status}
            muted={call.muted}
            durationSeconds={call.durationSeconds}
            error={call.error}
            onStart={call.start}
            onEnd={call.end}
            onToggleMute={call.toggleMute}
          />
          <LiveTranscript entries={call.transcript} />
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <DoctorList event={liveEvents.event} />
          <AppointmentTable event={liveEvents.event} />
        </section>
      </div>
    </main>
  );
}
