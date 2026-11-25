import { useEffect, useState } from "react";
import type { LiveEvent } from "../types";

export type LiveEventStatus = "connecting" | "connected" | "reconnecting";

export function useLiveEvents() {
  const [event, setEvent] = useState<LiveEvent | null>(null);
  const [status, setStatus] = useState<LiveEventStatus>("connecting");

  useEffect(() => {
    let disposed = false;
    let hasConnected = false;
    let retryDelay = 500;
    let reconnectTimer: number | undefined;
    let socket: WebSocket | undefined;

    const connect = () => {
      if (disposed) return;

      setStatus(hasConnected ? "reconnecting" : "connecting");
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const currentSocket = new WebSocket(`${protocol}//${window.location.host}/ws/events`);
      socket = currentSocket;

      currentSocket.onopen = () => {
        hasConnected = true;
        retryDelay = 500;
        setStatus("connected");
      };

      currentSocket.onmessage = (message) => {
        try {
          const nextEvent = JSON.parse(message.data) as LiveEvent;
          if (typeof nextEvent.topic === "string" && nextEvent.data) {
            setEvent(nextEvent);
          }
        } catch {
          // Ignore malformed event frames and keep the connection alive.
        }
      };

      currentSocket.onclose = () => {
        if (disposed) return;
        setStatus("reconnecting");
        reconnectTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 10_000);
      };

      currentSocket.onerror = () => currentSocket.close();
    };

    connect();
    return () => {
      disposed = true;
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, []);

  return { event, status };
}