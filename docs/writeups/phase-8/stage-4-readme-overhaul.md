# Phase 8, Stage 4 - README overhaul

## What is being implemented

`README.md` rewritten from its Phase 0 state (a 4-step quickstart and nothing else) into what `ROADMAP.md`'s own Phase 8 bullet calls for: an architecture diagram, a rubric summary, and placeholders for ablation results and a demo GIF - plus updated quickstart/development/deployment sections reflecting all 7 phases actually built since Phase 0, none of which the old README mentioned at all (no API, no dashboard, no orchestration, no Docker Compose beyond `postgres`/`minio`).

- **A Mermaid architecture diagram** covering every real component (ingestion, Postgres+pgvector, MinIO/S3, the feature pipeline, the fusion model, Prefect orchestration, the FastAPI service, the React dashboard) and a table mapping each layer to the phase that built it and a one-line description - both new content, not adapted from anywhere, but every claim in them was cross-checked against the actual codebase rather than written from memory (e.g. confirmed `slop smoke` still exists in `cli.py` before citing it in the quickstart).
- **A rubric summary** - the definition of "slop," the 4 signal categories (mass-produced/templated, misleading thumbnail-title mismatch, low information density, explicitly-not-slop counterexamples), and an honest note that the rubric was revised once real labeling surfaced edge cases the first draft missed (per `docs/rubric.md`'s own text) - condensed from `docs/rubric.md`, which is linked rather than duplicated in full.
- **A "Results" section stating plainly that no real videos have been labeled yet**, with concrete placeholders for what will go there (an ablation table, per Phase 4 Stage 13's format; a SHAP interaction report, per Phase 4 Stage 14; a demo GIF, once a public deployment exists to record one against) - each placeholder links to the exact stage write-up that documents the real command/format to fill it in with, rather than a vague "TODO."
- **A "Deployment" section** covering both the local docker-compose path (Phase 8 Stage 2's `web`+`api` services) and the AWS reference path (Phase 8 Stage 3's Terraform), stating explicitly that the Terraform has never been applied.

## What it should look like

The README now reads as a real project front page rather than a Phase 0 scaffold - see `README.md` directly for the full rendered content. Every command shown in it (`docker compose up -d`, `uv sync`, `uv run slop smoke`, `cd web && npm install`, `uv run uvicorn sloppy.api.app:app --reload --port 8000`, `npm run dev`, `uv run pytest`, `npx vitest run`, etc.) was cross-checked against what actually exists in this repository right now - none of it is copy-pasted from an earlier phase's write-up without verifying it still applies.

## What to look out for

- **The "Results" section is deliberately honest about having nothing to show yet**, rather than either omitting the section entirely or filling it with synthetic/fabricated numbers to look more complete. This matches the project's consistent stance throughout every phase's write-ups: real data blockers are stated plainly, not hidden or worked around cosmetically. A reader (or a portfolio reviewer) should come away knowing exactly what's real (the full pipeline, genuinely built and tested) versus what's still pending (real labels, real ablation results, a real public demo).
- **The architecture diagram is a Mermaid `flowchart`, which GitHub renders natively** in a README, but not every Markdown viewer does - this is a reasonable bet for a project's primary README (GitHub is by far the most likely place it's read), not a universal guarantee.
- **This README does not document Phase 7's `slop orchestrate serve`/scheduled-refresh commands in the quickstart** - deliberately: those are meaningful once `data/seed_channels.csv` has real tracked channels in it, which it doesn't yet, so surfacing them prominently in the very first thing a reader sees would be premature. They're referenced in the architecture table and left fully documented in `docs/writeups/phase-7/`, one click away.
- **No demo GIF, screenshot, or rendered diagram image was created** - the Mermaid diagram is text-based (rendered by the Markdown viewer, not a static image asset), and no GIF exists because no public deployment exists yet to record one against, exactly as the Results section says.

## How to run tests properly

No automated tests apply to a README - its own "correctness" is that every command and file reference in it actually exists and works, which was checked directly (grepping `cli.py` for `smoke`, confirming `web/`'s `npm run dev`/`npx vitest run`/`npm run lint` scripts exist from Phase 6, confirming `infra/terraform/README.md` and every `docs/writeups/phase-N/stage-M-*.md` path linked from it actually exists) rather than assumed from memory of earlier phases.

```powershell
uv run pytest    # unaffected - no application code changed in this stage
uv run ruff format --check README.md
```
