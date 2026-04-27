import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';
import type { LedgerEntry } from '../api/types';

export function useLedger() {
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      const res = await apiClient.get<LedgerEntry[]>('/ledger/');
      setEntries(res.data);
      setError(null);
    } catch {
      setError('Failed to load ledger');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
    const interval = setInterval(fetch, 5000);
    return () => clearInterval(interval);
  }, [fetch]);

  return { entries, loading, error, refetch: fetch };
}
