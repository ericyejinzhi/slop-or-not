import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ScoreBadge } from './ScoreBadge'

describe('ScoreBadge', () => {
  it('shows "Unscored" when score/predictedLabel are null', () => {
    render(<ScoreBadge score={null} predictedLabel={null} />)
    expect(screen.getByText('Unscored')).toBeInTheDocument()
  })

  it('shows the label and score for a "down" prediction', () => {
    render(<ScoreBadge score={0.873} predictedLabel="down" />)
    expect(screen.getByText('down (0.87)')).toBeInTheDocument()
  })

  it('shows the label and score for an "up" prediction', () => {
    render(<ScoreBadge score={0.1} predictedLabel="up" />)
    expect(screen.getByText('up (0.10)')).toBeInTheDocument()
  })
})
