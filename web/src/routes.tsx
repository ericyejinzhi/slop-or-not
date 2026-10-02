import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ChannelViewPage } from './pages/ChannelViewPage'
import { LabeledVideosPage } from './pages/LabeledVideosPage'
import { LabelingPage } from './pages/LabelingPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { VideoDetailPage } from './pages/VideoDetailPage'
import { VideoGridPage } from './pages/VideoGridPage'

// Extracted from App.tsx (which wraps this in BrowserRouter) so tests can wrap it in a
// MemoryRouter instead, without duplicating the route tree.
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<VideoGridPage />} />
        <Route path="videos/:videoId" element={<VideoDetailPage />} />
        <Route path="channels/:channelId" element={<ChannelViewPage />} />
        <Route path="label" element={<LabelingPage />} />
        <Route path="labeled" element={<LabeledVideosPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
