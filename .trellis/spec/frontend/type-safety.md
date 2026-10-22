# Types and HTTP Boundaries

Applies to frontend types and API changes; extracted 2026-10-21.

- `frontend/tsconfig.json` enables strict checking. Shared response/request types live in `frontend/src/types/video.ts` and `types/collections.ts`; component-local props can stay in their component file.
- `frontend/src/api/videos.ts` and `api/collections.ts` unwrap axios responses and encode path IDs with encodeURIComponent. Keep snake_case wire fields consistent with backend Pydantic schemas rather than silently renaming one side.
- Axios generic annotations are compile-time declarations, not runtime JSON validators. `frontend/src/api/client.ts` accepts unknown errors, uses axios.isAxiosError, and checks error message/code types before exposing ApiError.
- Model the actual external interface narrowly: `features/video/youtube-api.ts` declares YouTubeApi/YouTubeInstance and optional window globals; `YouTubePlayer.tsx` exposes its own smaller handle.
- Read nullable/optional values and discriminants from shared types. `hasCurrentChunkLayout` in `features/transcript/TranscriptViewSwitch.tsx` checks revision identity and segment coverage before enabling layout-dependent rendering.

Avoid using a cast to manufacture a server guarantee. Some existing test fixtures use casts/any (for example `frontend/src/App.test.tsx`); this baseline does not claim the entire repository is cast-free. Boundary examples and error/encoding checks: `frontend/src/api/videos.test.ts` and `api/collections.test.ts`.
