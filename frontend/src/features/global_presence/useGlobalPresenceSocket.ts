// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * useGlobalPresenceSocket -- app-wide presence WebSocket.
 *
 * Connects to /api/v1/global_presence/ws/?token=<jwt> and keeps the
 * global presence store in sync with the server roster. Sends
 * `route_update` on pathname changes and `status_update` when the tab
 * becomes hidden or the user goes idle for 3 minutes.
 *
 * Unlike the per-entity usePresenceWebSocket (collab_locks), this hook:
 *   - auto-reconnects with jittered exponential backoff,
 *   - tracks idle/active status from visibility + input events,
 *   - is designed to be mounted once at the AppLayout level.
 *
 * Graceful: if the WS never connects nothing renders.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';

import { useAuthStore } from '@/stores/useAuthStore';
import {
  useGlobalPresenceStore,
  type GlobalPresenceUser,
} from '@/stores/useGlobalPresenceStore';

/* ── Protocol messages ─────────────────────────────────────────────── */

interface PresenceSnapshot {
  event: 'presence_snapshot';
  users: GlobalPresenceUser[];
}

interface PresenceJoin {
  event: 'presence_join';
  user: GlobalPresenceUser;
}

interface PresenceLeave {
  event: 'presence_leave';
  user_id: string;
}

interface PresenceUpdate {
  event: 'presence_update';
  user: GlobalPresenceUser;
}

interface Pong {
  event: 'pong';
}

type ServerMessage =
  | PresenceSnapshot
  | PresenceJoin
  | PresenceLeave
  | PresenceUpdate
  | Pong;

/* ── Constants ─────────────────────────────────────────────────────── */

/** Base delay for the first reconnect attempt (ms). */
const BASE_DELAY_MS = 1_000;
/** Maximum backoff ceiling (ms). */
const MAX_DELAY_MS = 30_000;
/** User is considered idle after this much inactivity (ms). */
const IDLE_TIMEOUT_MS = 3 * 60 * 1_000;
/** How often we ping to keep the connection alive (ms). */
const PING_INTERVAL_MS = 25_000;

/* ── Helpers ───────────────────────────────────────────────────────── */

/** Exponential backoff with full jitter: `random(0, min(cap, base * 2^attempt))`. */
function jitteredBackoff(attempt: number): number {
  const ceiling = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt);
  return Math.random() * ceiling;
}

/* ── Hook ──────────────────────────────────────────────────────────── */

/**
 * Mount once at AppLayout level. The hook is a pure side-effect -- it
 * returns nothing. All state is written to `useGlobalPresenceStore`.
 */
export function useGlobalPresenceSocket(): void {
  const location = useLocation();
  const pathnameRef = useRef(location.pathname);
  pathnameRef.current = location.pathname;

  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isIdleRef = useRef(false);
  const mountedRef = useRef(true);

  const { setUsers, upsertUser, removeUser, setWsStatus, clear } =
    useGlobalPresenceStore.getState();

  /* ── Send helper (safe even when socket is not open) ─────────── */
  const send = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  /* ── Idle detection ──────────────────────────────────────────── */
  const resetIdleTimer = useCallback(() => {
    if (idleTimerRef.current !== null) {
      clearTimeout(idleTimerRef.current);
    }
    if (isIdleRef.current) {
      isIdleRef.current = false;
      send({ type: 'status_update', status: 'active' });
    }
    idleTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return;
      isIdleRef.current = true;
      send({ type: 'status_update', status: 'idle' });
    }, IDLE_TIMEOUT_MS);
  }, [send]);

  /* ── Connect / reconnect ─────────────────────────────────────── */
  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const token = useAuthStore.getState().accessToken;
    if (!token) {
      setWsStatus('closed');
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url =
      `${protocol}//${window.location.host}` +
      `/api/v1/global_presence/ws/` +
      `?token=${encodeURIComponent(token)}`;

    setWsStatus('connecting');
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      setWsStatus('error');
      scheduleReconnect();
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setWsStatus('open');
      retryRef.current = 0;

      // Report current route immediately after handshake.
      send({ type: 'route_update', route: pathnameRef.current });

      // Keep-alive pings.
      pingTimerRef.current = setInterval(() => {
        send({ type: 'ping' });
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (msg: MessageEvent<string>) => {
      let parsed: ServerMessage;
      try {
        parsed = JSON.parse(msg.data) as ServerMessage;
      } catch {
        return;
      }

      switch (parsed.event) {
        case 'presence_snapshot':
          setUsers(parsed.users);
          break;
        case 'presence_join':
          upsertUser(parsed.user);
          break;
        case 'presence_leave':
          removeUser(parsed.user_id);
          break;
        case 'presence_update':
          upsertUser(parsed.user);
          break;
        case 'pong':
          // No-op, connection is alive.
          break;
      }
    };

    ws.onerror = () => {
      if (!mountedRef.current) return;
      setWsStatus('error');
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setWsStatus('closed');
      cleanupTimers();
      scheduleReconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    const delay = jitteredBackoff(retryRef.current);
    retryRef.current += 1;
    retryTimerRef.current = setTimeout(() => {
      retryTimerRef.current = null;
      connect();
    }, delay);
  }, [connect]);

  const cleanupTimers = useCallback(() => {
    if (pingTimerRef.current !== null) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  /* ── Lifecycle: connect on mount, teardown on unmount ─────────── */
  useEffect(() => {
    mountedRef.current = true;
    connect();

    // Idle: visibility change immediately marks idle.
    const onVisibility = () => {
      if (document.hidden) {
        if (idleTimerRef.current !== null) clearTimeout(idleTimerRef.current);
        isIdleRef.current = true;
        send({ type: 'status_update', status: 'idle' });
      } else {
        resetIdleTimer();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);

    // Idle: user input resets the 3-minute timer.
    const onActivity = () => resetIdleTimer();
    document.addEventListener('mousemove', onActivity, { passive: true });
    document.addEventListener('keydown', onActivity, { passive: true });
    document.addEventListener('pointerdown', onActivity, { passive: true });

    // Start the idle timer.
    resetIdleTimer();

    return () => {
      mountedRef.current = false;
      document.removeEventListener('visibilitychange', onVisibility);
      document.removeEventListener('mousemove', onActivity);
      document.removeEventListener('keydown', onActivity);
      document.removeEventListener('pointerdown', onActivity);
      if (retryTimerRef.current !== null) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      if (idleTimerRef.current !== null) {
        clearTimeout(idleTimerRef.current);
        idleTimerRef.current = null;
      }
      cleanupTimers();
      try {
        wsRef.current?.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
      clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── Send route_update on pathname change ────────────────────── */
  useEffect(() => {
    send({ type: 'route_update', route: location.pathname });
  }, [location.pathname, send]);
}
