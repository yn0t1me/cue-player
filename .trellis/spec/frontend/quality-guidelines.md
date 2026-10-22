# Frontend Verification

Applies to frontend changes; extracted 2026-10-21.

## Commands

Run from `frontend/` using WSL Node/npm from [shared engineering rules](../guides/project-engineering.md):

```bash
npm test
npm run build
```

`frontend/package.json` defines test as vitest run and build as tsc --noEmit followed by vite build. There is no lint command; do not report a nonexistent lint check as passed.

## Useful test seams

- Pure behavior: `frontend/src/features/transcript/findActiveSegmentIndex.test.ts` and `markText.test.ts`.
- HTTP contract/error mapping: `frontend/src/api/videos.test.ts` and `collections.test.ts` substitute the axios adapter and inspect requests/responses.
- UI interaction: `frontend/src/features/transcript/ReaderNotesControls.test.tsx`, `pages/VideoPage.test.tsx`, and `features/video/YouTubePlayer.test.tsx` use jsdom, React act/createRoot and controlled API/player dependencies. Preserve teardown, mock restoration and QueryClient cleanup as applicable (see `App.test.tsx`).

Choose behavior checks for the changed boundary, including errors and lifecycle effects. Do not add a new test framework merely to match an external template. Real playback, fullscreen and browser controls require browser/YouTube checks and an explicit evidence note; a mocked API or player cannot prove them. Documentation-only changes use reference/link and consistency checks without claiming application regression tests were rerun.
