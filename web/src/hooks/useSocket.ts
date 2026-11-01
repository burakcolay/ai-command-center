import { useEffect, useRef, useState } from "react";
import type { WsMessage } from "../lib/types";

/** Live updates from the backend. Reconnects with backoff; `onReconnect` lets callers refetch. */
export function useSocket(onMessage: (m: WsMessage) => void, onReconnect: () => void) {
  const handlers = useRef({ onMessage, onReconnect });
  handlers.current = { onMessage, onReconnect };
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry = 0;
    let timer: number | undefined;
    let closed = false;
    let everConnected = false;

    const open = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${location.host}/ws`);
      socket.onopen = () => {
        if (everConnected) handlers.current.onReconnect();
        everConnected = true;
        retry = 0;
        setConnected(true);
      };
      socket.onmessage = (e) => handlers.current.onMessage(JSON.parse(e.data));
      socket.onclose = () => {
        setConnected(false);
        if (closed) return;
        timer = window.setTimeout(open, Math.min(500 * 2 ** retry++, 8000));
      };
    };
    open();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, []);

  return connected;
}
