# Component Boundaries

Applies to React UI work; extracted 2026-10-21.

## Patterns to follow

- Use typed props and explicit callbacks for user intent. `frontend/src/features/transcript/TranscriptViewSwitch.tsx` receives mode, availability and onChange; it does not fetch or publish subtitles.
- Keep imperative browser APIs behind a narrow interface. `frontend/src/features/video/YouTubePlayer.tsx` exposes `PlayerHandle.seekTo(seconds): boolean` and `play(): boolean`, keeping the YouTube instance private. Check the readiness result before continuing an action.
- Compose persistence actions at the owning workflow boundary: `frontend/src/pages/VideoPage.tsx` passes create/update/delete callbacks to `useReaderNotes` rather than teaching selection controls endpoint paths.
- Preserve loading, pending, failure and success feedback when changing an action. `frontend/src/features/collections/RetryVideoButton.tsx` disables a pending mutation and uses role=alert/status for feedback; `TranscriptViewSwitch.tsx` uses aria-pressed.

## Lifecycle

`VideoPage` keys `VideoPageContent` by video ID to reset local state across videos. `YouTubePlayer` destroys the old instance and clears timers on cleanup. Avoid keeping a previous video's player, editor draft or callback alive after route changes. Behavior examples are in `frontend/src/features/video/YouTubePlayer.test.tsx` and `frontend/src/pages/VideoPage.test.tsx`; jsdom assertions alone do not establish live player behavior.
