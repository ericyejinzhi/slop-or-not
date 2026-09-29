import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="text-center">
      <p className="text-slate-600">Page not found.</p>
      <Link to="/" className="text-slate-900 underline">
        Back to videos
      </Link>
    </div>
  )
}
