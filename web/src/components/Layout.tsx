import { Link, NavLink, Outlet } from 'react-router-dom'
import { usePredictEnabled, useReadOnly } from '../api/hooks'

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `rounded px-3 py-1.5 text-sm font-medium ${
    isActive ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
  }`
}

export function Layout() {
  // Both labeling pages write labels (the Labeled page can relabel a video), so a
  // read-only deployment has nothing useful to show there.
  const readOnly = useReadOnly()
  // The check-a-video page needs a model and a YouTube key on the server; hide it otherwise.
  const predictEnabled = usePredictEnabled()

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <nav className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-3">
          <Link to="/" className="text-lg font-semibold text-slate-900">
            slop-or-not
          </Link>
          {predictEnabled && (
            <NavLink to="/check" className={navLinkClass}>
              Check a video
            </NavLink>
          )}
          <NavLink to="/" end className={navLinkClass}>
            Videos
          </NavLink>
          <NavLink to="/channels" className={navLinkClass}>
            Channels
          </NavLink>
          {!readOnly && (
            <>
              <NavLink to="/label" className={navLinkClass}>
                Label
              </NavLink>
              <NavLink to="/labeled" className={navLinkClass}>
                Labeled
              </NavLink>
            </>
          )}
        </nav>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
