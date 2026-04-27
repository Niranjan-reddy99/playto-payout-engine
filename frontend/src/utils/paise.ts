// NEVER do float math. Only convert at display time.
export function paiseToCurrency(paise: number): string {
  return (Math.floor(paise) / 100).toFixed(2);
}

export function currencyToPaise(inr: string): number {
  return Math.round(parseFloat(inr) * 100);
}

export function generateIdempotencyKey(): string {
  return crypto.randomUUID();
}

export function formatINR(inr: string): string {
  const num = parseFloat(inr);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
  }).format(num);
}
