# Slop-or-Not dashboard (`web/`)

React + TypeScript + Vite, with Tailwind and TanStack Query. It talks to the FastAPI backend
through `/api/*` (the Vite dev server proxies to `localhost:8000`; in production nginx proxies
to the `api` container).

## Pages (`src/pages/`)

| Route | Page | Notes |
|---|---|---|
| `/` | Videos grid | sort and filter, score badges |
| `/videos/:videoId` | Video detail | score, feature breakdown, similar videos |
| `/channels` | Channels | ranked by channel score |
| `/channels/:channelId` | Channel view | channel score and its videos |
| `/check` | Check a video | paste a YouTube link, get a score; changes nothing in the dataset |
| `/label`, `/labeled` | Labeling and labeled-videos review | hidden when the API reports `read_only` |

The ingest form and the labeling links are hidden when `GET /config` reports
`read_only: true` (a public deployment). The Check a video link shows when `predict_enabled`
is true.

## Commands

```powershell
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
npx vitest run     # tests (the Vitest pool is set to threads for Windows)
npm run lint       # oxlint
npm run build      # production bundle; web/Dockerfile + nginx.conf serve it
```

Project-wide docs: [../README.md](../README.md). Build notes for this app:
[../docs/writeups/phase-6/](../docs/writeups/phase-6/).
