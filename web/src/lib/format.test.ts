import { describe, expect, it } from 'vitest'
import { formatCount, formatDate, formatNumber } from './format'

describe('formatNumber', () => {
  it('formats to 2 decimal places by default', () => {
    expect(formatNumber(0.87345)).toBe('0.87')
  })

  it('respects a custom digit count', () => {
    expect(formatNumber(0.87345, 3)).toBe('0.873')
  })

  it('returns "-" for null or undefined', () => {
    expect(formatNumber(null)).toBe('-')
    expect(formatNumber(undefined)).toBe('-')
  })
})

describe('formatCount', () => {
  it('adds thousands separators', () => {
    expect(formatCount(1234567)).toBe('1,234,567')
  })

  it('returns "-" for null', () => {
    expect(formatCount(null)).toBe('-')
  })
})

describe('formatDate', () => {
  it('formats an ISO string as a readable date', () => {
    expect(formatDate('2026-01-15T00:00:00Z')).toContain('2026')
  })
})
