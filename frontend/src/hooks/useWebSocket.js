/** TraceLit — useWebSocket hook for real-time paper processing progress */
import { useEffect, useRef, useState, useCallback } from 'react';

const WS_RECONNECT_DELAY = 3000;
const WS_MAX_RETRIES = 5;

/**
 * WebSocket hook for real-time paper processing progress.
 * Connects to the backend WebSocket endpoint and provides
 * status, last message, and a manual send function.
 *
 * @param {string} url - WebSocket URL (e.g. ws://localhost:8000/ws/papers/progress)
 * @param {object} options - { onMessage, enabled }
 */
export default function useWebSocket(url, { onMessage, enabled = true } = {}) {
  const [status, setStatus] = useState('disconnected');
  const [lastMessage, setLastMessage] = useState(null);
  const wsRef = useRef(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!url || !enabled) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        retriesRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLastMessage(data);
          onMessageRef.current?.(data);
        } catch {
          // Non-JSON message, store raw
          setLastMessage(event.data);
        }
      };

      ws.onclose = (event) => {
        setStatus('disconnected');
        wsRef.current = null;
        // Auto-reconnect unless closed cleanly or max retries exceeded
        if (!event.wasClean && retriesRef.current < WS_MAX_RETRIES) {
          retriesRef.current += 1;
          setStatus('reconnecting');
          reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_DELAY);
        }
      };

      ws.onerror = () => {
        setStatus('error');
        // onclose will fire after onerror and handle reconnect
      };
    } catch (err) {
      console.warn('WebSocket connection failed:', err);
      setStatus('error');
    }
  }, [url, enabled]);

  useEffect(() => {
    if (!enabled || !url) {
      setStatus('disconnected');
      return;
    }

    connect();

    return () => {
      clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmount');
        wsRef.current = null;
      }
    };
  }, [url, enabled, connect]);

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }, []);

  return { status, lastMessage, send };
}
