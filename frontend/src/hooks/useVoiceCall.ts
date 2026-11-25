import { useEffect, useRef, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import type { TranscriptEntry } from "../types";

export type VoiceCallStatus = "idle" | "connecting" | "connected" | "ended" | "error";

function connectionErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  const name = error instanceof Error ? error.name : "";

  if (
    name === "NotAllowedError" ||
    name === "PermissionDeniedError" ||
    normalized.includes("permission denied") ||
    normalized.includes("not allowed")
  ) {
    return "Microphone access was denied. Allow microphone access in your browser and try again.";
  }

  if (
    normalized.includes("failed to fetch") ||
    normalized.includes("network") ||
    normalized.includes("connection refused") ||
    normalized.includes("not found") ||
    normalized.includes("502") ||
    normalized.includes("503")
  ) {
    return "Could not reach the voice backend. Check that it is running and /api/offer is available.";
  }

  return message || "Could not start the voice call.";
}

export function useVoiceCall() {
  const clientRef = useRef<PipecatClient | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement>(null);
  const remoteStreamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const [status, setStatus] = useState<VoiceCallStatus>("idle");
  const [muted, setMuted] = useState(false);
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);

  const addTranscript = (
    role: TranscriptEntry["role"],
    text: string,
    final: boolean,
    stableId?: string,
  ) => {
    const cleanText = text.trim();
    if (!cleanText) return;

    setTranscript((entries) => {
      const stableIndex = stableId
        ? entries.findIndex((entry) => entry.id === stableId)
        : -1;
      const pendingIndex =
        stableIndex === -1 && entries.at(-1)?.role === role && !entries.at(-1)?.final
          ? entries.length - 1
          : stableIndex;

      if (pendingIndex !== -1) {
        return entries.map((entry, index) =>
          index === pendingIndex ? { ...entry, text: cleanText, final } : entry,
        );
      }

      return [
        ...entries,
        {
          id: stableId ?? `${role}-${Date.now()}-${Math.random()}`,
          role,
          text: cleanText,
          final,
        },
      ];
    });
  };

  const finishCall = () => {
    if (startedAtRef.current !== null) {
      setDurationSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
      startedAtRef.current = null;
    }
    setMuted(false);
    setStatus((current) => (current === "error" ? "error" : "ended"));
    remoteStreamRef.current = null;
    if (remoteAudioRef.current) {
      remoteAudioRef.current.pause();
      remoteAudioRef.current.srcObject = null;
    }
  };

  const start = async () => {
    if (status === "connecting" || status === "connected") return;

    setTranscript([]);
    setError(null);
    setMuted(false);
    setDurationSeconds(0);
    startedAtRef.current = null;
    setStatus("connecting");

    const remoteStream = new MediaStream();
    remoteStreamRef.current = remoteStream;
    const remoteAudio = remoteAudioRef.current;
    if (remoteAudio) {
      remoteAudio.srcObject = remoteStream;
      remoteAudio.muted = false;
      void remoteAudio.play().then(
        () => console.info("[voice] remote audio playback unlocked from call click"),
        (playError: unknown) => console.warn("[voice] initial audio play failed", playError),
      );
    }

    const transport = new SmallWebRTCTransport({
      webrtcRequestParams: { endpoint: "/api/offer" },
    });
    const client = new PipecatClient({
      transport,
      enableMic: true,
      callbacks: {
        onConnected: () => {
          console.info("[voice] client connected");
          startedAtRef.current ??= Date.now();
          setStatus("connected");
        },
        onDisconnected: () => {
          console.info("[voice] client disconnected");
          finishCall();
        },
        onError: (message) => {
          console.error("[voice] client error", message);
          setError("The voice connection encountered an error. Check the backend and try again.");
          setStatus("error");
        },
        onTransportStateChanged: (transportState) => {
          console.info("[voice] transport state", transportState);
          if (transportState === "error") {
            setError("The voice connection failed. Check that the backend is running.");
            setStatus("error");
          }
        },
        onBotReady: (data) => {
          console.info("[voice] bot ready; RTVI version", data.version);
        },
        onTrackStarted: (track, participant) => {
          console.info("[voice] track started", {
            kind: track.kind,
            id: track.id,
            readyState: track.readyState,
            participant,
          });
          if (track.kind !== "audio" || participant?.local !== false) return;

          const stream = remoteStreamRef.current ?? new MediaStream();
          remoteStreamRef.current = stream;
          if (!stream.getTracks().some((existingTrack) => existingTrack.id === track.id)) {
            stream.addTrack(track);
          }
          const audio = remoteAudioRef.current;
          if (!audio) {
            console.error("[voice] remote audio element is missing");
            return;
          }
          audio.srcObject = stream;
          void audio.play().then(
            () => console.info("[voice] remote audio playback started"),
            (playError: unknown) => console.error("[voice] remote audio playback failed", playError),
          );
        },
        onTrackStopped: (track, participant) => {
          console.info("[voice] track stopped", {
            kind: track.kind,
            id: track.id,
            participant,
          });
          if (track.kind === "audio" && participant?.local === false) {
            remoteStreamRef.current?.removeTrack(track);
          }
        },
        onUserInput: (data) => {
          if (data.input_type === "transcription") {
            console.info("[voice] user transcript", { final: data.final, text: data.text });
            addTranscript("user", data.text, data.final);
          }
        },
        onBotOutput: (data) => {
          const text = data.spoken_progress?.accumulated_text ?? data.text;
          if (!text.trim()) return;
          console.info("[voice] bot output", { status: data.spoken_status, text });
          const final = data.spoken_status !== "new" && data.spoken_status !== "in-progress";
          const stableId = data.segment_id === undefined ? undefined : `assistant-${data.segment_id}`;
          addTranscript("assistant", text, final, stableId);
        },
      },
    });
    clientRef.current = client;

    try {
      await client.connect();
      console.info("[voice] connect() resolved");
      startedAtRef.current ??= Date.now();
      setStatus("connected");
    } catch (connectError) {
      console.error("[voice] connect() failed", connectError);
      clientRef.current = null;
      await client.disconnect().catch(() => undefined);
      setError(connectionErrorMessage(connectError));
      setStatus("error");
    }
  };

  const end = async () => {
    const client = clientRef.current;
    if (!client) {
      setStatus((current) => (current === "idle" ? "idle" : current));
      return;
    }

    clientRef.current = null;
    try {
      await client.disconnect();
    } catch {
      setError("The call ended, but the transport did not close cleanly.");
    } finally {
      finishCall();
    }
  };

  const toggleMute = () => {
    const client = clientRef.current;
    if (!client) return;
    const nextMuted = !muted;
    client.enableMic(!nextMuted);
    setMuted(nextMuted);
  };

  useEffect(() => {
    if (status !== "connected") return;

    const updateDuration = () => {
      if (startedAtRef.current !== null) {
        setDurationSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }
    };
    updateDuration();
    const interval = window.setInterval(updateDuration, 1000);
    return () => window.clearInterval(interval);
  }, [status]);

  useEffect(
    () => () => {
      const client = clientRef.current;
      if (client) void client.disconnect().catch(() => undefined);
    },
    [],
  );

  return {
    status,
    muted,
    durationSeconds,
    error,
    transcript,
    remoteAudioRef,
    start,
    end,
    toggleMute,
  };
}