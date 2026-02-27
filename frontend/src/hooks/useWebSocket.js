/** TraceLit — useWebSocket hook (Phase 2 — placeholder) */
import { useEffect, useRef, useState } from 'react';

/**
 * WebSocket hook for real-time paper processing progress.
 * Phase 2 implementation — currently a no-op stub.
 */
export default function useWebSocket(url) {
  const [status, setStatus] = useState('disconnected');
  const [lastMessage, setLastMessage] = useState(null);
  const wsRef = useRef(null);

  useEffect(() => {
    // WebSocket connection will be implemented in Phase 2
    // For now, polling via REST is used
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [url]);

  return { status, lastMessage };
}
