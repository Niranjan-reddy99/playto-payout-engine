import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { Balance } from '../api/types';

export function useBalance() {
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // useCallback so the function reference stays stable across renders.
  // Without this, putting `fetch` in the useEffect dependency array would
  // cause an infinite loop (new function reference → re-run effect → repeat).
  const fetch = useCallback(async () => {
    try {
      const res = await apiClient.get<Balance>('/balance/');
      setBalance(res.data);
      setLastUpdated(new Date());
      setError(null);
    } catch {
      setError('Failed to load balance');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch(); // load immediately on mount
    const interval = setInterval(fetch, 5000); // then refresh every 5 seconds
    return () => clearInterval(interval); // clean up when component unmounts
  }, [fetch]);

  return { balance, loading, error, lastUpdated, refetch: fetch };
}
