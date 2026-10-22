# Frontend Directory and Dependency Boundaries

Applies to frontend engineering; extracted 2026-10-21.

- `frontend/src/main.tsx` composes StrictMode, QueryClientProvider and BrowserRouter; `frontend/src/App.tsx` owns route declarations.
- `frontend/src/pages/` composes routed workflows. `VideoPage.tsx` wires data, player and favorites; `ImportBatchPage.tsx` owns batch status display.
- `frontend/src/features/library/`, `features/video/`, `features/transcript/` and `features/collections/` hold domain UI and related helpers/tests. `components/VideoStatus.tsx` is shared display.
- `frontend/src/api/client.ts` owns HTTP transport and error conversion; `api/videos.ts` and `api/collections.ts` own endpoint calls. Pages/components consume those functions rather than adding independent HTTP clients.
- `frontend/src/types/video.ts` and `types/collections.ts` hold shared wire shapes. The frontend communicates through HTTP, not by importing backend implementation.
- CSS currently lives in `frontend/src/styles.css`; source tests are colocated as `*.test.ts` / `*.test.tsx`.

## Actual examples and traps

`frontend/src/features/transcript/ReaderNotesControls.tsx` contains `useReaderFavorites`; there is currently no `src/hooks/` directory. Reuse the existing feature placement; a directory sketch does not require creating empty modules. `features/collections/shared.ts` owns collection helpers; avoid making a repository-wide utils directory merely to host one feature helper.

References: the source paths above and `frontend/package.json`. Keep the Vite SPA and simple CSS architecture; a UI framework, global state library or SSR architecture requires a separately scoped decision.
