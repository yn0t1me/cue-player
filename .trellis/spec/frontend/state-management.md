# State Ownership and Query Cache

Applies to frontend persistence and UI state; extracted 2026-10-21.

## Ownership

- TanStack Query owns server state. `frontend/src/main.tsx` creates one app QueryClient with automatic retries disabled for queries and mutations.
- React state owns transient UI: playback time, active tab, reading mode, fullscreen and translation visibility in `frontend/src/pages/VideoPage.tsx`.
- Refs own imperative handles or intent identity. `frontend/src/features/collections/RetryVideoButton.tsx` retains its IntentKey instance with useRef; `shared.ts` keeps a key stable for the same retry payload. Do not regenerate it merely because a response was lost.

## Keys and refresh

Include the resource identity and relevant version in query keys. Current examples are `['video', id]`, `['transcript', id]` and `['chunk-layout', id, revision_id]` in VideoPage. Invalidate related cache families after a mutation; collection changes use `refreshLibrary` in `frontend/src/features/collections/shared.ts`, while favorite writes refresh marks in VideoPage; publication also refreshes current transcript/layout and historical favorite context.

Processing polling is conditional: `features/video/ProcessingState.tsx` owns videoRefreshInterval; `pages/ImportBatchPage.tsx` polls while waiting/running items exist. Avoid permanent polling for terminal states or a second local copy of the same server result. Existing components may coordinate several queries; adding Redux/Zustand is not part of this baseline.
