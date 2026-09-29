export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return '-'
  return value.toFixed(digits)
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return value.toLocaleString()
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
