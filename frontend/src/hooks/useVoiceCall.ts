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
  const remoteAudioTrackRef = useRef<MediaStreamTrack | null>(null);
  const disconnectRequestedRef = useRef(false);
  const startedAtRef = useRef<number | null>(null);
  const [status, setStatus] = useState<VoiceCallStatus>("idle");
  const [muted, setMuted] = useState(false);
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);

  const attachBotAudioTrack = (track: MediaStreamTrack) => {
    remoteAudioTrackRef.current = track;
    const audio = remoteAudioRef.current;
    if (!audio) return;

    audio.srcObject = new MediaStream([track]);
    void audio.play().catch(console.error);
    console.info("bot audio track attached");
  };

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
    remoteAudioTrackRef.current = null;
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
    disconnectRequestedRef.current = false;
    setStatus("connecting");

    const remoteAudio = remoteAudioRef.current;
    if (remoteAudio) {
      remoteAudio.srcObject = new MediaStream();
      remoteAudio.muted = false;
      void remoteAudio.play().catch(console.error);
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
          if (!disconnectRequestedRef.current) {
            setError("The voice connection was lost. Start a new call to try again.");
            setStatus("error");
          }
          finishCall();
        },
        onError: (message) => {
          console.error("[voice] client error", message);
          const errorData = message.data as { fatal?: boolean; error?: string };
          if (errorData.fatal) {
            setError(errorData.error || "The voice connection encountered a fatal error.");
            setStatus("error");
          }
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
          if (track.kind !== "audio" || participant?.local) return;
          attachBotAudioTrack(track);
        },
        onTrackStopped: (track, participant) => {
          console.info("[voice] track stopped", {
            kind: track.kind,
            id: track.id,
            participant,
          });
          if (track.kind === "audio" && !participant?.local) {
            if (remoteAudioTrackRef.current?.id === track.id) {
              remoteAudioTrackRef.current = null;
              if (remoteAudioRef.current) {
                remoteAudioRef.current.pause();
                remoteAudioRef.current.srcObject = null;
              }
            }
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
      const botAudioTrack = client.tracks().bot?.audio;
      if (botAudioTrack) attachBotAudioTrack(botAudioTrack);
      startedAtRef.current ??= Date.now();
      setStatus("connected");
    } catch (connectError) {
      console.error("[voice] connect() failed", connectError);
      clientRef.current = null;
      disconnectRequestedRef.current = true;
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
    disconnectRequestedRef.current = true;
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
    () => {
      const track = remoteAudioTrackRef.current;
      if (track) attachBotAudioTrack(track);
    },
    [],
  );

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