// Shared "who is labeling" identity, persisted client-side so it survives a page reload.
// Used by both LabelingPage (session labeling) and LabeledVideosPage (relabeling).
const LABELER_STORAGE_KEY = 'slop-or-not:labeler'

export function readStoredLabeler(): string {
  try {
    return localStorage.getItem(LABELER_STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function writeStoredLabeler(value: string): void {
  try {
    localStorage.setItem(LABELER_STORAGE_KEY, value)
  } catch {
    // best-effort only - labeling still works without persistence
  }
}
