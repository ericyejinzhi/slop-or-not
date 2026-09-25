# The Slop Rubric

## 1. Purpose & scope

This document exists so that "slop or not" means the same thing on day 1 and day 30 of labeling, and the same thing whether the video in front of you is a gaming channel or a cooking channel. Labeling ~300-500 videos will take multiple sessions spread over more than a week; without a written definition, judgment drifts - a video that gets `down` on Monday might get `up` on Friday just because the last ten videos were worse. This doc is also the intellectual core of the whole project: it's the operational definition the rest of the pipeline (features, model, evaluation) is ultimately trying to predict, so it belongs in the README as much as in this repo.

This rubric governs Phase 2 labeling only. It does not define sub-labels or reasons (e.g. "this is slop because of the title") - that kind of decomposition is handled unsupervised, from signals the model discovers itself, in Phase 4.

## 2. Definition of slop

**Slop** is content optimized to capture attention or watch time with as little effort as possible, at the expense of being honest, original, or informative about what it actually delivers. The tell isn't low budget or low polish - it's a mismatch between what the video promises (via title, thumbnail, upload pattern) and what a viewer actually gets, or a lack of any real information/effort once you get past the packaging. A video can be cheaply made and still not be slop (see 3D below); a video can be expensively produced and still be slop.

## 3. Signal categories

Each category below lists what to look for, 2-3 concrete examples, and a counter-example - something that resembles the category but isn't slop. A video doesn't need to hit every category to be `down`; one strong signal is often enough. Absence of all these signals is a strong `up`.

### A. Mass-produced / templated

The video is one of many near-identical outputs from the same channel (or the same production pipeline across channels), where the specific subject matter is interchangeable filler around a fixed format.

- A channel posting daily "Top 10 X" videos with the same intro, outro, stock B-roll, and text-to-speech narration, where X changes but nothing else does.
- An AI-narrated "compilation" channel stitching together clips from other creators with no added commentary, uploading multiple times a day.
- A thumbnail template (same bold red arrow, same shocked-face inset photo, same font) reused across dozens of unrelated videos.

**Counter-example:** A cooking channel that uses the same intro bumper and recipe-card outro on every video, but each video is a genuinely different recipe demonstrated hands-on by the creator. A consistent format is not the same as a templated, interchangeable one - ask whether the substance changes or only the label on the box changes.

### B. Misleading thumbnail-title mismatch

The packaging (title + thumbnail) promises something the video doesn't deliver, designed to generate a click or an emotional reaction that the content doesn't earn.

- Thumbnail shows a shocked/crying face reacting to something that never happens in the video, or a screenshot that isn't actually from the video.
- Title poses a dramatic question ("Is this the end of X?!") that the video answers with "no, not really" in the first ten seconds, if it answers it at all.
- Numbers or claims in the title that don't match the content ("$1,000,000 CHALLENGE" for a video where no such sum appears).

**Counter-example:** A documentary titled "The Man Who Vanished Twice" that withholds the resolution until the end - this is a legitimate narrative device (intentional mystery), not a lie about content, as long as the video is actually *about* the mystery it names. The test is whether the title/thumbnail describe the video's real subject, not whether they build suspense.

### C. Low information density

Once you strip the packaging, there's little actual content, information, or effort - the video pads its runtime or its existence without adding anything a viewer couldn't get faster elsewhere.

- A 20-minute video that could be a 2-minute video: extensive recapping of what's about to be said, restating the title's premise three different ways before getting to the point, filler transitions.
- Pure reaction content (watching and reacting to someone else's video) that adds no analysis, expertise, or new information beyond "here is my face while this plays."
- A "news" video that just reads a press release or another outlet's article aloud over stock footage, with no original reporting or analysis.

**Counter-example:** A slow, meditative video (a long unedited nature walk, a real-time cooking process) that is intentionally low-pace but genuinely delivers what it promises, with no padding relative to its own premise. Slow isn't the same as padded - padded means content is stretched beyond what the subject actually supports.

### D. Explicitly NOT slop

These are patterns that can *look* like red flags in isolation but are not, on their own, evidence of slop. Calling them out explicitly matters because the labeling pool deliberately includes "boring mid-tier" channels, not just obvious slop farms vs. beloved creators - low production value must not become a proxy for the label.

- Low production value (a static webcam, poor audio, minimal editing) that is otherwise honest and informative - e.g. a plain screen-recorded coding tutorial that does exactly what its title says.
- A small or unpolished channel that uploads infrequently and isn't chasing a formula, even if the videos are unremarkable.
- Simple, direct titles and thumbnails with no hook at all ("How to Change a Bike Chain") - the absence of clickbait is not itself suspicious.

## 4. Out of scope for Phase 2

No sub-labels are recorded during labeling - not "why," not a category from Section 3, not a confidence score. The label is a single up/down/skip judgment on the whole video. Decomposing *why* something reads as slop (title intent, thumbnail lure, etc.) is handled unsupervised in Phase 4, from signals the model finds on its own; hand-labeling reasons here would just be duplicating that work with less rigor, and would bias the model toward categories a human happened to think of.

## 5. Edge cases / tie-breakers

- **Compilation channels with real editorial effort** (a genuinely curated "best moments" video with original commentary/analysis tying clips together) are judged on the added effort, not penalized just for using others' clips - contrast with category A's uncommented stitch-jobs.
- **Kids' content** is judged the same as anything else: does it deliver what it promises without padding or a misleading hook, regardless of production polish. "It's for kids" is not a pass.
- **AI-voice tutorials that are still substantive** (correct, specific, actually walks through the stated task) are not automatically slop just because the narration is synthetic - category A is about interchangeable, low-effort *content*, not about the presence of AI narration by itself. An AI-narrated video that's accurate and specific can be `up`; an AI-narrated video that's generic filler is `down` on content grounds, not narration grounds.
- **Official trailers/clips/announcements** uploaded by a rights-holder are judged as what they are (a promotional artifact), not held to the same "information density" bar as long-form content - a 30-second trailer isn't slop for being short.
- **When genuinely torn between up and down**, use `skip` rather than guessing. A guess adds noise to the training label; a skip just means this video sits out this round and can be revisited later once the rubric is sharper.

## 6. Worked examples

| Video description | Category triggered | Verdict | Reasoning |
|---|---|---|---|
| Daily "Top 10 Craziest Animal Moments" upload, stock clips, TTS narration, same thumbnail template for 200+ videos | A | `down` | Textbook templated mass-production; subject is interchangeable filler |
| "You won't BELIEVE what this dog did!!" thumbnail of a dog mid-air, video is 90 seconds of an unremarkable dog trick | B | `down` | Thumbnail/title promise drama the content doesn't deliver |
| 25-minute "iPhone 17 review" that spends 15 minutes restating the announcement and rumors before showing the phone at all | C | `down` | Runtime padded well beyond what the actual content (a hands-on review) requires |
| Static-camera home-cook video, plain title "Simple Weeknight Fried Rice," walks through the recipe accurately, no hook, mediocre lighting | D | `up` | Low polish but honest and informative - exactly what it says it is |
| Documentary-style video "The Building Nobody Remembers," slow reveal of a real historical mystery, resolved thoughtfully by the end | B (superficially) | `up` | Intentional mystery framing that pays off - matches its real subject, not a bait-and-switch |
| AI-narrated but well-researched and accurate "History of the Roman Aqueducts" with specific dates, sources implied, no filler | A (superficially) | `up` | Synthetic voice, but the content itself is specific and substantive, not interchangeable filler |
| Official 30-second movie teaser uploaded by the studio's channel | (none - edge case 5) | `up` | Judged as a promotional artifact, not held to information-density standards |
| A mid-tier let's-play channel, unremarkable but plays the stated game start to finish with genuine commentary, plain thumbnail | (none) | `up` | Boring but honest - the "mid-tier" case the corpus deliberately needs |
| Reaction video: creator watches a viral clip and just says "wow" and "no way" repeatedly, no analysis added | C | `down` | Zero information added beyond the source clip itself |
| A video that's clearly trying to have it both ways - moderately clickbaity title, but content is mostly on-topic and only mildly padded | - | `skip` | Genuinely borderline; better to skip than force a noisy guess |

## 7. Labeling protocol

Every video gets exactly one of three judgments, one keystroke each in the labeling CLI:

- **`up`** - quality / not slop.
- **`down`** - slop.
- **`skip`** - can't confidently judge; sits out this round.

This polarity (`up` = good, `down` = slop) is fixed and will be echoed as an on-screen legend in the labeling CLI so it's never ambiguous mid-session which key means what.
