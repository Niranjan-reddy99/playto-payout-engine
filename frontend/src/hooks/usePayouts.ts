import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../api/client';
import type { PayoutRequest } from '../api/types';

export function usePayouts() {
  const [payouts, setPayouts] = useState<PayoutRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // useRef instead of useState because we don't want changing this to
  // trigger a re-render. It's just bookkeeping for the comparison below.
  const prevStatusMap = useRef<Record<string, string>>({});

  // IDs of payouts whose status changed since the last poll.
  // Used by PayoutHistory to flash a yellow highlight on those rows.
  const [changedIds, setChangedIds] = useState<Set<string>>(new Set());

  const fetch = useCallback(async () => {
    try {
      const res = await apiClient.get<PayoutRequest[]>('/payouts/');
      setPayouts(res.data);

      // Compare each payout's current status against what we saw last poll.
      // If it changed (e.g. pending → completed), add it to changedIds.
      const newChanged = new Set<string>();
      res.data.forEach((p) => {
        const prev = prevStatusMap.current[p.id];
        if (prev && prev !== p.status) {
          newChanged.add(p.id);
        }
        prevStatusMap.current[p.id] = p.status; // update our record for next poll
      });

      if (newChanged.size > 0) {
        setChangedIds(newChanged);
        setTimeout(() => setChangedIds(new Set()), 3000); // clear highlight after 3s
      }

      setError(null);
    } catch {
      setError('Failed to load payouts');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
    const interval = setInterval(fetch, 5000); // poll every 5 seconds for live updates
    return () => clearInterval(interval);
  }, [fetch]);

  return { payouts, loading, error, changedIds, refetch: fetch };
}
