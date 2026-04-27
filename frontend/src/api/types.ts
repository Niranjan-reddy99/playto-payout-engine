export interface Balance {
  available_paise: number;
  held_paise: number;
  total_paise: number;
  available_inr: string;
  held_inr: string;
  total_inr: string;
}

export interface PayoutRequest {
  id: string;
  amount_paise: number;
  amount_inr: string;
  bank_account_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  attempts: number;
  created_at: string;
  updated_at: string;
}

export interface LedgerEntry {
  id: string;
  entry_type: 'credit' | 'debit' | 'hold' | 'unhold';
  amount_paise: number;
  amount_inr: string;
  description: string;
  payout: string | null;
  created_at: string;
}
