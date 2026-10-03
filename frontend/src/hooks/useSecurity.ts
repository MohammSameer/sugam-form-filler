import { useEffect, useRef, useState } from "react";
import { getSecurity, type SecurityEvent } from "@/lib/adk";

/**
 * Polls the security checkpoint's feed.
 *
 * Polling, not SSE: these events are emitted *between* model calls and are very
 * low-volume, so a second event-stream racing the agent's own would add a
 * connection and a failure mode to buy nothing. We poll faster while a turn is
 * in flight (that is when the checkpoint actually fires) and back off when idle.
 */
export function useSecurity(active: boolean) {
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [checksPassed, setChecksPassed] = useState(0);
  const cursor = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      try {
        const snap = await getSecurity(cursor.current);
        if (cancelled) return;
        if (snap.events.length) {
          cursor.current = snap.cursor;
          // Newest first, and bounded — the panel is a live feed, not an archive.
          setEvents((prev) => [...snap.events.reverse(), ...prev].slice(0, 40));
        }
        setChecksPassed(snap.checksPassed);
      } catch {
        // A failed poll is not worth surfacing; the next one will catch up.
      }
      if (!cancelled) {
        timer = window.setTimeout(tick, active ? 1200 : 5000);
      }
    };

    tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [active]);

  return { events, checksPassed };
}
