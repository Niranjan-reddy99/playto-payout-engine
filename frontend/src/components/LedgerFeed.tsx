import { useLedger } from '../hooks/useLedger';
import { formatINR } from '../utils/paise';

const ENTRY_STYLES: Record<string, { border: string; prefix: string; icon: string }> = {
  credit: { border: 'border-l-4 border-green-400', prefix: '+', icon: '' },
  debit:  { border: 'border-l-4 border-red-400',   prefix: '-', icon: '' },
  hold:   { border: 'border-l-4 border-amber-400', prefix: '',  icon: '🔒' },
  unhold: { border: 'border-l-4 border-blue-400',  prefix: '',  icon: '🔓' },
};

const AMOUNT_COLOR: Record<string, string> = {
  credit: 'text-green-700',
  debit:  'text-red-700',
  hold:   'text-amber-700',
  unhold: 'text-blue-700',
};

export function LedgerFeed() {
  const { entries, loading, error } = useLedger();

  if (loading) return <div className="bg-white rounded-xl p-6 shadow text-gray-500">Loading ledger...</div>;
  if (error) return <div className="bg-white rounded-xl p-6 shadow text-red-500">{error}</div>;

  return (
    <div className="bg-white rounded-xl shadow overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-lg font-semibold text-gray-800">Ledger</h2>
      </div>
      <div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
        {entries.length === 0 ? (
          <p className="p-6 text-gray-500 text-sm">No ledger entries.</p>
        ) : (
          entries.map((entry) => {
            const style = ENTRY_STYLES[entry.entry_type];
            return (
              <div key={entry.id} className={`px-4 py-3 ${style.border}`}>
                <div className="flex justify-between items-center">
                  <div>
                    <p className="text-sm text-gray-700">{entry.description}</p>
                    <div className="flex gap-3 mt-0.5">
                      {entry.payout && (
                        <span className="text-xs text-gray-400 font-mono">
                          payout {entry.payout.slice(0, 8)}…
                        </span>
                      )}
                      <span className="text-xs text-gray-400">
                        {new Date(entry.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <span className={`font-semibold text-sm ${AMOUNT_COLOR[entry.entry_type]}`}>
                    {style.icon}{style.prefix}{formatINR(entry.amount_inr)}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
