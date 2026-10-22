# Hooks and Browser Lifecycles

Applies to stateful React code; extracted 2026-10-21.

- Custom hooks use the `use` prefix and currently live beside the feature they support: `useReaderFavorites` in `frontend/src/features/transcript/ReaderNotesControls.tsx`. Follow this real placement; no central hooks package exists.
- Use TanStack Query for server reads. In `frontend/src/pages/VideoPage.tsx`, queryFn forwards AbortSignal to the API helper and enabled guards prevent dependent reads before data is available.
- Keep external subscriptions paired with cleanup. `VideoPage.tsx` disconnects ResizeObserver/removes resize listeners; `frontend/src/features/video/YouTubePlayer.tsx` clears interval/timeout, marks the effect inactive and destroys the player.
- Refs hold imperative instances and current callbacks; state drives rendering. The player updates its callback ref without rebuilding the instance for every playback tick.
- Keep asynchronous completion guarded after unmount/reinitialization. `frontend/src/features/video/youtube-api.ts` shares its pending load and resets it on failure so a later attempt can retry.

Evidence: `ReaderNotesControls.test.tsx`, `YouTubePlayer.test.tsx` and `youtube-api.test.ts` beside those source files. When changing dependencies or cleanup, verify unmount, route replacement, delayed readiness and retry rather than asserting only first mount.
