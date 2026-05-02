import { useState, useEffect } from 'react';

/**
 * useLiveClock — returns a live 24-hour time string updated every second.
 * @returns {string} formatted time, e.g. "23:42:07"
 */
export function useLiveClock() {
  const [time, setTime] = useState(() =>
    new Date().toLocaleTimeString('en-US', { hour12: false })
  );

  useEffect(() => {
    const id = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-US', { hour12: false }));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return time;
}
