import { useState, useEffect, useRef, useCallback } from 'react';

export default function useCollaboration(projectId) {
  const [connected, setConnected] = useState(false);
  const [users, setUsers] = useState([]);
  const [locks, setLocks] = useState({});
  const [lastUpdate, setLastUpdate] = useState(null);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${projectId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'init':
          setLocks(data.locks || {});
          setUsers(data.users || []);
          break;
        case 'user_joined':
        case 'user_left':
          setUsers(data.users || []);
          break;
        case 'chapter_locked':
          setLocks(prev => ({ ...prev, [data.chapter]: { user_id: data.user_id } }));
          break;
        case 'chapter_unlocked':
          setLocks(prev => {
            const next = { ...prev };
            delete next[data.chapter];
            return next;
          });
          break;
        case 'chapter_updated':
          setLastUpdate({
            chapter: data.chapter,
            user_id: data.user_id,
            char_count: data.char_count,
            timestamp: Date.now(),
          });
          // Also unlock
          setLocks(prev => {
            const next = { ...prev };
            delete next[data.chapter];
            return next;
          });
          break;
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto-reconnect after 3s
      reconnectRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [projectId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const lockChapter = useCallback((chapter) => {
    wsRef.current?.send(JSON.stringify({ action: 'lock', chapter }));
  }, []);

  const unlockChapter = useCallback((chapter) => {
    wsRef.current?.send(JSON.stringify({ action: 'unlock', chapter }));
  }, []);

  const saveChapter = useCallback((chapter, content, summary) => {
    wsRef.current?.send(JSON.stringify({ action: 'save', chapter, content, summary }));
  }, []);

  return {
    connected,
    users,
    locks,
    lastUpdate,
    lockChapter,
    unlockChapter,
    saveChapter,
  };
}
