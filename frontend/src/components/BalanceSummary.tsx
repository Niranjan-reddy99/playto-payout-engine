import { useBalance } from '../hooks/useBalance';
import { formatINR } from '../utils/paise';

export function BalanceSummary() {
  const { balance, loading, error, lastUpdated } = useBalance();

  if (loading) return <div className="bg-white rounded-xl p-6 shadow text-gray-500">Loading balance...</div>;
  if (error) return <div className="bg-white rounded-xl p-6 shadow text-red-500">{error}</div>;
  if (!balance) return null;

  return (
    <div className="bg-white rounded-xl p-6 shadow">
      <h2 className="text-sm font-medium text-gray-500 mb-1">Available Balance</h2>
      <p className="text-4xl font-bold text-green-600">{formatINR(balance.available_inr)}</p>
      <div className="mt-3 flex gap-6 text-sm">
        <div>
          <span className="text-gray-500">Held: </span>
          <span className="font-medium text-amber-600">{formatINR(balance.held_inr)}</span>
        </div>
        <div>
          <span className="text-gray-500">Total earned: </span>
          <span className="font-medium text-gray-700">{formatINR(balance.total_inr)}</span>
        </div>
      </div>
      {lastUpdated && (
        <p className="mt-2 text-xs text-gray-400">
          Updated {lastUpdated.toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
