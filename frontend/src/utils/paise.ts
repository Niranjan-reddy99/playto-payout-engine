// All money on the backend is stored as paise (integer).
// 1 INR = 100 paise. We only convert to INR for display — never for calculation.
// Rule: never do float arithmetic on money. 0.1 + 0.2 = 0.30000000000000004 in JS.
// Math.round() when converting to paise ensures we never get a fractional paise.

// Convert paise (integer) → INR string for display e.g. 37500 → "375.00"
export function paiseToCurrency(paise: number): string {
  return (Math.floor(paise) / 100).toFixed(2);
}

// Convert what the user typed (e.g. "375.50") → paise integer (37550) for the API
export function currencyToPaise(inr: string): number {
  return Math.round(parseFloat(inr) * 100);
}

// Each payout submission gets a fresh UUID so retrying a failed form submit
// creates a new payout rather than replaying the old one.
export function generateIdempotencyKey(): string {
  return crypto.randomUUID();
}

// Format paise as a localised INR currency string e.g. 37500 → "₹375.00"
export function formatINR(inr: string): string {
  const num = parseFloat(inr);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
  }).format(num);
}
