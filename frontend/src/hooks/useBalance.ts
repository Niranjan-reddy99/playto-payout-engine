import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { Balance } from '../api/types';

export function useBalance() {
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

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
    fetch();
    const interval = setInterval(fetch, 5000);
    return () => clearInterval(interval);
  }, [fetch]);

  return { balance, loading, error, lastUpdated, refetch: fetch };
}
