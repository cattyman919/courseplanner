# Demo video

`make demo-video` records and renders `demo/output/coursepath-demo.mp4`. It is about 4 minutes
long, 1080p at 60 fps, with an offline voice, burned-in captions and a toggleable subtitle
track. Setup, files and iteration tips are in [demo/README.md](../demo/README.md). The design
decision is D11 in [decisions.md](decisions.md).

## Pipeline

```text
narration.ts ──global-setup──► Kokoro (uv run tts/kokoro_tts.py) ──► .cache/tts/*.wav + line lengths
     │                                                                  │
demo.spec.ts (Playwright, 1600×900 @2x) ── say(): caption + actions, waits for the line
     │   zoom()/click() markers, trace + video.webm
     ▼
render.ts (playwright-recast):
  parse → speedUp (real time; only dead time is skipped)
        → subtitlesFromTrace → textProcessing
        → autoZoom (clicks 1.35×) + explicit zooms (1.1–2.2×, 550 ms ease-in-out)
        → cursorOverlay (450 ms glide) → clickEffect (blue ripple)
        → voiceover(Kokoro, loudness-normalised)
        → render 1080p60, burned + embedded subtitles → duration check (180–300 s)
```

## Storyboard

| # | Scene | Shows |
|---|---|---|
| 0 | intro | What CoursePath is: symbolic AI, no ML or LLM |
| 1 | planner | On-track: 3 terms, 29 credits, cost 4.45. A* expands 4 states vs BFS 14 and UCS 15. |
| 2 | explain | Transfer: 4 terms with catch-up badges. "Why CS301" shows PREREQ, then forward chaining. The log filtered to CONFLICT shows CS210/MATH210. |
| 3 | creditCap | 12 credits: still 3 terms. BFS 58, UCS 69, A* 26. |
| 4 | graph | The AI401 prerequisite chain, linked to the A* heuristic |
| 5 | watch | Step, Play, Run to end; the green solution path; BFS's wider tree |
| 6 | build | AI320 locked (PREREQ), SYS330 PRUNED, AI picks a term, commit, plan the rest, accept |
| 7 | saved | Save to SQLite, then Load and Delete with confirmation |
| 8 | outro | Summary |

## Editing

- **Wording:** change `demo/narration.ts`. Only changed lines are re-synthesized, since the
  cache is keyed on text, voice and speed.
- **Pronunciation:** `speakable()` in `kokoro-provider.ts` changes only what the voice
  says, e.g. "CS301" → "C S three oh one" and "A*" → "A-star". The captions keep the
  original text.
- **Camera:** each `focus(locator, level, hold)` call in `demo.spec.ts` is one zoom. Global
  zoom, cursor and click settings live in `render.ts`.
- **Length:** the render fails outside 3–5 minutes. Trim or extend narration lines to fix
  it.
