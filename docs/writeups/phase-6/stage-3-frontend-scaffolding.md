# Phase 6, Stage 3 - Vite + React + TS + Tailwind + Vitest scaffolding

## What is being implemented

The frontend toolchain, in `web/` (the directory Phase 0 reserved for this back at project scaffolding time). Scaffolded via `npm create vite@latest . -- --template react-ts` (React 19, Vite 8, TypeScript 6), then extended with:

- **Tailwind CSS v4** via `@tailwindcss/vite` (a Vite plugin, not the older PostCSS-config setup) - `src/index.css` is just `@import 'tailwindcss';`.
- **React Router** (`react-router-dom`) and **TanStack Query** (`@tanstack/react-query` + devtools) installed now, wired up starting Stage 4/5 - not used yet in this stage's placeholder `App.tsx`.
- **Vitest + React Testing Library + `@testing-library/jest-dom` + `msw`** for testing, matching the confirmed decision to give the frontend comparable rigor to the backend's test suite. `src/test/setup.ts` wires up `jest-dom` matchers and an MSW (`msw/node`) server's lifecycle (`listen`/`resetHandlers`/`close`); `src/test/mocks/server.ts` is an empty `setupServer()` for now - real request handlers get added once the API client exists (Stage 4).
- `strict: true` added explicitly to `tsconfig.app.json` - the scaffolded template did not enable it by default (confirmed by inspecting the generated file), which was surprising enough to flag and fix rather than assume was intentional.
- A dev-server proxy in `vite.config.ts` (`/api/* -> http://localhost:8000/*`, stripping the `/api` prefix) - lets the frontend call relative `/api/...` URLs during `npm run dev` without hitting CORS at all, since FastAPI never got `CORSMiddleware` added in Phase 5. The API client (Stage 4) will use `/api` as its base URL.
- `oxlint` (the linter `create-vite` scaffolds by default now - a fast Rust-based linter, a similar tooling philosophy to the backend's `ruff`) kept as-is rather than swapped for ESLint.

## What it should look like

```
$ cd web
$ npm install
$ npm run build
✓ 16 modules transformed.
dist/index.html                   0.46 kB │ gzip:  0.29 kB
dist/assets/index-*.css           6.72 kB │ gzip:  2.03 kB
dist/assets/index-*.js          219.77 kB │ gzip: 68.66 kB
✓ built in ~500ms

$ npx vitest run
 Test Files  1 passed (1)
      Tests  1 passed (1)

$ npm run lint
> oxlint
(no output = no issues)

$ npm run dev
# http://localhost:5173 renders a centered "slop-or-not" heading, Tailwind-styled
```

All four commands were actually run, not just described - confirmed clean end to end, including a real `curl` against the running dev server.

## What to look out for

- **A real environment bug found and fixed**: Vitest's default `forks` test-runner pool failed to start on this Node 24/Windows combination - every test run hung for the full 60-second timeout, then reported `Error: [vitest-pool]: Failed to start forks worker` / `Timeout waiting for worker to respond`, with zero tests actually running. Fixed by setting `test.pool: 'threads'` in `vite.config.ts` (worker_threads instead of child_process forks) - confirmed working immediately after (test run dropped from 60s timeout to ~6-20s real execution). This is now documented in `docs/writeups/TODO.md` item 16 as a first-thing-to-check if frontend tests ever seem to hang on another machine, rather than something to assume is a real test failure.
- **`strict: true` was missing from the scaffolded `tsconfig.app.json`** - not a bug exactly (the file scaffolds correctly per Vite's current template), but surprising enough given every backend phase's insistence on real type/lint rigor (ruff's E/W/F/I/UP/B rule set) that it was added explicitly rather than left to chance. Re-verified `tsc -b` and `vite build` both stay clean with it on.
- **Tailwind v4's setup is CSS-first** - no `tailwind.config.js` was created, and none is needed for basic usage (content scanning is automatic in v4 via the Vite plugin). If custom theme tokens are needed in a later stage (e.g. matching a specific color palette for score badges), that's where a `tailwind.config.js`/CSS `@theme` block would be introduced - not needed yet.
- **The `/api` dev-proxy is a deliberate way to avoid ever touching CORS configuration on the FastAPI side.** This only applies to `npm run dev` (Vite's dev server) - a production build (`npm run build`, or Phase 8's eventual AWS deployment) would need its own reverse-proxy or CORS story, explicitly out of scope for this phase.
- `dist/` (the build output) is git-ignored (confirmed in `web/.gitignore`, which `create-vite` generates correctly) and was deleted after each verification run in this stage - it's a build artifact, not something to keep around.
- Every dependency for the frontend lives in `web/package.json`/`package-lock.json`, entirely separate from the backend's `uv.lock` - `npm install` must be run inside `web/`, not the repo root.

## How to run tests properly

```powershell
cd web
npm install          # first time only, or after pulling a package.json change
npx tsc -b            # type-check
npm run build         # type-check + production bundle
npx vitest run        # test suite, single run (not watch mode)
npm run lint          # oxlint
npm run dev           # dev server at http://localhost:5173 (proxies /api to :8000)
```

No backend changes were made in this stage - `uv run pytest` (158 passed, 5 deselected as of Stage 2) is unaffected and doesn't need re-running for this stage specifically, though it's still worth confirming nothing regressed given both stacks share the same repo.
