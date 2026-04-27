import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '../api/client';
import type { PayoutRequest } from '../api/types';

export function usePayouts() {
  const [payouts, setPayouts] = useState<PayoutRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const prevStatusMap = useRef<Record<string, string>>({});
  const [changedIds, setChangedIds] = useState<Set<string>>(new Set());

  const fetch = useCallback(async () => {
    try {
      const res = await apiClient.get<PayoutRequest[]>('/payouts/');
      setPayouts(res.data);

      const newChanged = new Set<string>();
      res.data.forEach((p) => {
        if (prevStatusMap.current[p.id] && prevStatusMap.current[p.id] !== p.status) {
          newChanged.add(p.id);
        }
        prevStatusMap.current[p.id] = p.status;
      });
      if (newChanged.size > 0) {
        setChangedIds(newChanged);
        setTimeout(() => setChangedIds(new Set()), 3000);
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
    const interval = setInterval(fetch, 5000);
    return () => clearInterval(interval);
  }, [fetch]);

  return { payouts, loading, error, changedIds, refetch: fetch };
}
