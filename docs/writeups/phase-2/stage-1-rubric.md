# Phase 2, Stage 1 - docs/rubric.md (written definition of "slop")

## What is being implemented

The written definition of "slop" that every later Phase 2 stage depends on: the labeling CLI (Stage 5) will echo its up/down/skip polarity on screen, and every human judgment made during labeling is supposed to trace back to this document. No code in this stage - just content.

File: `docs/rubric.md` (new).

## What it should look like

A 7-section document:

1. Purpose & scope - why a written rubric matters for a multi-week, multi-session labeling effort.
2. A one-paragraph definition of slop (packaging-vs-delivery mismatch, or low effort/information once you strip the packaging).
3. Four signal categories, each with 2-3 concrete examples and one counter-example: **A** mass-produced/templated, **B** misleading thumbnail-title mismatch, **C** low information density, **D** explicitly-not-slop (guards against conflating low budget with slop).
4. What's explicitly out of scope for Phase 2 (no sub-labels/reasons - that's Phase 4's job, unsupervised).
5. Five edge cases/tie-breakers (compilations with real editorial effort, kids' content, AI-narrated-but-substantive tutorials, official trailers, genuine ambiguity -> use skip).
6. A 10-row worked-examples table pairing a video description with a category, verdict, and one-line reasoning - including cases where a category superficially applies but the verdict goes the other way (e.g. a mystery-framed documentary that isn't actually misleading).
7. The labeling protocol itself: `up` = quality/not-slop, `down` = slop, `skip` = can't judge.

## What to look out for

- **This is a first draft meant to be argued with, not a finished spec.** The roadmap itself expects the rubric (and the related severity-score question) to get revised after the first ~50 real labels once you've actually sat with real videos - don't treat the categories or the worked examples as fixed until you've stress-tested them against real content.
- I made an editorial call on category D (explicitly-not-slop) because the roadmap's corpus-shape rules deliberately include the "boring mid-tier," not just obvious slop farms vs. beloved creators - without an explicit counter-category, low production value could silently become a proxy for the label during labeling, which would bias the corpus. Worth reading this section particularly closely since it's the one most likely to need tightening once you see real mid-tier channels.
- The worked-examples table intentionally includes two rows where a category name appears in parentheses but the verdict goes the *other* way (a documentary framed as mysterious that's still honest, and an AI-narrated video that's still substantive) - these are meant to demonstrate that hitting a category's surface pattern isn't automatically disqualifying; the point is always whether the content delivers on its own promise.
- Nothing here talks about severity/confidence scoring - per the plan, that's explicitly deferred to a possible follow-up decision after ~50 labels, so the rubric doesn't currently define a 0-3 scale.

## How to run tests properly

There's no code to test in this stage - this is a read/edit exercise:

```powershell
# Just open and read it
notepad docs/rubric.md
# or in your editor of choice
```

Read it end to end and edit anything that doesn't match your own judgment before Stage 5 (the labeling CLI) starts echoing its polarity on screen - the categories and the worked-examples table are the parts most worth pressure-testing, since those are what you'll actually be applying under time pressure across 300-500 videos.
