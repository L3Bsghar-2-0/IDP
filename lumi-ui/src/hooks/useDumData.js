import { useState, useEffect, useRef, useCallback } from 'react';

const RELAY_WS = (import.meta.env.VITE_DUM_RELAY_URL ?? 'http://localhost:3001')
  .replace(/\/$/, '')
  .replace(/^http/, 'ws') + '/ws';

// Match the relay server's STALE_AFTER / DOWN_AFTER defaults (ms).
const STALE_MS =  10_000;
const DOWN_MS  =  30_000;

/**
 * Connects to the DUM relay WebSocket and tracks the live model state.
 *
 * Returns:
 *   records    — raw record array from DUM
 *   summary    — summary object (may include model_version, averages, etc.)
 *   forecast   — time-series forecast array
 *   fetchedAt  — ISO timestamp of the last bundle (from DUM's perspective)
 *   status     — 'connecting' | 'live' | 'stale' | 'down'
 */
export function useDumData() {
  const [records,   setRecords]   = useState([]);
  const [summary,   setSummary]   = useState(null);
  const [forecast,  setForecast]  = useState([]);
  const [fetchedAt, setFetchedAt] = useState(null);
  const [status,    setStatus]    = useState('connecting');

  const lastTickRef  = useRef(null);
  const staleTimerRef = useRef(null);

  // ── stale / down detection ──────────────────────────────────────────────────
  const armStaleTimer = useCallback(() => {
    clearTimeout(staleTimerRef.current);
    staleTimerRef.current = setTimeout(() => {
      const age = Date.now() - (lastTickRef.current ?? 0);
      setStatus(age >= DOWN_MS ? 'down' : 'stale');
      // Recheck again after DOWN_MS - STALE_MS if we only went stale.
      if (age < DOWN_MS) {
        staleTimerRef.current = setTimeout(
          () => setStatus('down'),
          DOWN_MS - STALE_MS,
        );
      }
    }, STALE_MS);
  }, []);

  // ── message handler ─────────────────────────────────────────────────────────
  const onMessage = useCallback((event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    lastTickRef.current = Date.now();
    setRecords( msg.records   ?? []);
    setSummary( msg.summary   ?? null);
    setForecast(msg.forecast  ?? []);
    setFetchedAt(msg.fetched_at ?? null);
    setStatus('live');
    armStaleTimer();
  }, [armStaleTimer]);

  // ── connection lifecycle ────────────────────────────────────────────────────
  useEffect(() => {
    let ws;

    function connect() {
      setStatus('connecting');
      ws = new WebSocket(RELAY_WS);

      ws.onopen    = () => setStatus('connecting');   // waiting for first message
      ws.onclose   = () => { clearTimeout(staleTimerRef.current); setStatus('down'); }
      ws.onerror   = () => { clearTimeout(staleTimerRef.current); setStatus('down'); }
      ws.onmessage = onMessage;
    }

    connect();

    return () => {
      clearTimeout(staleTimerRef.current);
      ws?.close();
    };
  }, [onMessage]);

  return { records, summary, forecast, fetchedAt, status };
}
