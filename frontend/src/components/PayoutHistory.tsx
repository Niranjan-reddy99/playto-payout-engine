import { usePayouts } from '../hooks/usePayouts';
import { formatINR } from '../utils/paise';

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  processing: 'bg-amber-100 text-amber-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
};

export function PayoutHistory() {
  const { payouts, loading, changedIds } = usePayouts();

  if (loading) return <div className="bg-white rounded-xl p-6 shadow text-gray-500">Loading payouts...</div>;

  return (
    <div className="bg-white rounded-xl shadow overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-lg font-semibold text-gray-800">Payout History</h2>
      </div>
      {payouts.length === 0 ? (
        <p className="p-6 text-gray-500 text-sm">No payouts yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">ID</th>
                <th className="px-4 py-3 text-right">Amount</th>
                <th className="px-4 py-3 text-left">Bank</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {payouts.map((p) => (
                <tr
                  key={p.id}
                  className={`transition-colors ${changedIds.has(p.id) ? 'bg-yellow-50' : 'hover:bg-gray-50'}`}
                >
                  <td className="px-4 py-3 font-mono text-gray-600">{p.id.slice(0, 8)}...</td>
                  <td className="px-4 py-3 text-right font-medium text-gray-900">{formatINR(p.amount_inr)}</td>
                  <td className="px-4 py-3 text-gray-600">{p.bank_account_id}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_STYLES[p.status] || ''}`}>
                      {p.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(p.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
