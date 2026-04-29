import { useState, type FormEvent } from 'react';
import { apiClient } from '../api/client';
import { generateIdempotencyKey, currencyToPaise } from '../utils/paise';

const BANK_ACCOUNTS = [
  { value: 'HDFC_SAVINGS_001', label: 'HDFC Savings — ****001' },
  { value: 'ICICI_CURRENT_002', label: 'ICICI Current — ****002' },
  { value: 'SBI_001', label: 'SBI Savings — ****001' },
];

interface Props {
  onSuccess: () => void;
}

export function PayoutForm({ onSuccess }: Props) {
  const [amount, setAmount] = useState('');
  const [bankAccount, setBankAccount] = useState(BANK_ACCOUNTS[0].value);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [lastPayoutId, setLastPayoutId] = useState<string | null>(null);

  function showToast(type: 'success' | 'error', message: string) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 5000);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const amountPaise = currencyToPaise(amount);
    if (!amountPaise || amountPaise <= 0) {
      showToast('error', 'Enter a valid amount');
      return;
    }

    setLoading(true);
    // New idempotency key generated on each submit attempt
    const idempotencyKey = generateIdempotencyKey();

    try {
      const res = await apiClient.post(
        '/payouts/',
        { amount_paise: amountPaise, bank_account_id: bankAccount },
        { headers: { 'Idempotency-Key': idempotencyKey } }
      );
      setLastPayoutId(res.data.id);
      setAmount('');
      showToast('success', `Payout queued! ID: ${res.data.id.slice(0, 8)}...`);
      onSuccess();
    } catch (err: any) {
      const msg = err.response?.data?.error || 'Failed to create payout';
      showToast('error', msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-xl p-6 shadow">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Request Payout</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Amount (₹)</label>
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            required
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Bank Account</label>
          <select
            value={bankAccount}
            onChange={(e) => setBankAccount(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {BANK_ACCOUNTS.map((b) => (
              <option key={b.value} value={b.value}>{b.label}</option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white font-medium py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {loading ? 'Submitting...' : 'Request Payout'}
        </button>
      </form>

      {toast && (
        <div className={`mt-4 p-3 rounded-lg text-sm ${toast.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          {toast.message}
        </div>
      )}

      {lastPayoutId && (
        <p className="mt-2 text-xs text-gray-500">Last payout: <code className="bg-gray-100 px-1 rounded">{lastPayoutId}</code></p>
      )}
    </div>
  );
}
