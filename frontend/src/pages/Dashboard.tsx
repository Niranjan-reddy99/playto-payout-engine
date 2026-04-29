import { useCallback } from 'react';
import { BalanceSummary } from '../components/BalanceSummary';
import { PayoutForm } from '../components/PayoutForm';
import { PayoutHistory } from '../components/PayoutHistory';
import { LedgerFeed } from '../components/LedgerFeed';
import { apiClient, setCsrfToken } from '../api/client';

interface Props {
  onLogout: () => void;
}

export function Dashboard({ onLogout }: Props) {
  const handleLogout = useCallback(async () => {
    try {
      const response = await apiClient.post('/auth/logout/');
      setCsrfToken(response.data?.csrfToken);
    } finally {
      onLogout();
    }
  }, [onLogout]);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b shadow-sm">
        <div className="max-w-6xl mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Playto Payout Engine</h1>
            <p className="text-xs text-gray-500">Merchant Dashboard</p>
          </div>
          <button
            onClick={handleLogout}
            className="text-sm text-gray-600 hover:text-gray-900 border border-gray-300 px-3 py-1.5 rounded-lg hover:bg-gray-50 transition"
          >
            Sign Out
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <BalanceSummary />
          </div>
          <div>
            <PayoutForm onSuccess={() => {}} />
          </div>
        </div>

        <PayoutHistory />
        <LedgerFeed />
      </main>
    </div>
  );
}
