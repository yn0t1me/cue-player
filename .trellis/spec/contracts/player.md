# Player, Time and Browser Contracts

Extracted: 2026-10-21. Applies to current browser implementation, not a new policy/legal assertion. Detailed code examples: `frontend/src/features/video/YouTubePlayer.tsx`, `youtube-api.ts` and `LearningPlayer.tsx` in the same directory; `frontend/src/pages/VideoPage.tsx`.

## SDK and Lifecycle

Use the YouTube IFrame SDK with autoplay=0, playsinline=1, origin=window.location.origin and native controls retained. Shared script load and each player readiness have 15s timeouts. Loading failure resets pending loader so retry can recreate it; successful SDK stays reusable. PlayerHandle exposes seekTo(seconds):boolean and play():boolean; invalid/nonfinite/negative seek or not-ready/error/unmounted returns false and does not queue. A true return means an SDK command was sent, not confirmed playback success.

After readiness sample actual getCurrentTime every ~200ms and on relevant state-change callbacks. Do not advance a separate wall clock or assign a fictitious successful seek. Optional initialTime uses cueVideoById without autoplay and waits for actual playback state/time before reporting restored position. This low-level capability is not persistent resume or the retired standalone marks-page flow.

Changing videoId/retry/unmount marks old callbacks inactive, clears timers, destroys the player and clears its host/refs. Changing current-time callback alone does not rebuild the instance. Errors clear ready state and propagate readiness changes; VideoPage waits for genuine time before displaying a current subtitle. Playback success/failure never changes backend import job state.

## Active Sentence and Follow

`frontend/src/features/transcript/findActiveSegmentIndex.ts` selects start<=time<end; empty/nonfinite/gap => -1. Overlap chooses latest start, then later sequence_index, then later original-array index on a complete tie. It caches an independent sorted timeline by original array identity, binary-searches the last eligible start, and uses prefix maximum end to retain earlier long coverage. Return index belongs to the original display array, which is not sorted/mutated in place.

VideoPage queries details while processing (~2s), stops on terminal status and enables transcript after ready. Sentence replay calls seekTo(start) then play only if seek succeeded. Text dragging, Chinese or editor controls must not fall through to replay. `frontend/src/features/transcript/markText.ts` supplies Unicode code-point selections; `TranscriptPanel.tsx` guards the original gesture even if the browser selection was cleared by opening a menu.

TranscriptPanel auto-follow is local and defaults on. Programmatic scrolling changes only the transcript list, centers active item within scroll bounds and suppresses its own scroll event for a frame. Wheel/touch/scrollbar/navigation-key intent suspends follow. Return-to-current re-enables/positions without seek/play. Hidden tabs preserve scroll/follow; editing suspends follow without pausing video. Fullscreen, draft guards and collection directory toggle do not change player key; VideoPageContent is keyed by video ID for a real cross-video reset.

## Layout and Fullscreen

List and overlay share current-time-derived active sentence and revision-valid chunk mode. Chunk DOM retains canonical spaces for copy/selection; no chunk-level play clock exists. Preview/list/overlay Chinese toggles are independent page state; layout uses the matching revision and segment coverage.

ResizeObserver/window resize measures video/text; overlay keeps 48px top +64px bottom engineering allowance. If full English/Chinese cannot fit, dock beneath video rather than truncate or create synthetic timing. Ordinary overlay pointer-events pass through; explicit adjustment uses bounded relative coordinates and pointer capture, arrow-key movement and Home/reset. Docked subtitles cannot be dragged. Chinese never becomes the English selection root.

Request fullscreen on the outer application host, only in user interaction; sync actual state via Promise/fullscreenchange, handle rejection/Esc, exit only if this host owns fullscreen, restore trigger focus and clean up listeners. Cross-origin iframe DOM/control/advertisement state is unavailable to application code; do not rely on private interfaces, force-disable CC or claim detection of ads. Native iframe/PiP/mobile system fullscreen does not guarantee the application subtitle accompanies it. Do not infer official permission from successful technical tests.

## Evidence and Unresolved Limits

Test sources: `frontend/src/features/video/YouTubePlayer.test.tsx`, `youtube-api.test.ts`, `LearningPlayer.test.tsx`; `frontend/src/features/transcript/findActiveSegmentIndex.test.ts`, `TranscriptPanel.test.tsx`, `markText.test.ts`; `frontend/src/pages/VideoPage.test.tsx`. These verify controlled boundaries, not current real YouTube behavior.

The deferred Chrome native-controls issue remains unfixed: playback was reported to respond to picture clicks while native buttons were invisible. No cause is established. Before a future fix, reproduce with real YouTube and record video, viewport, ordinary/application fullscreen, hover and playback state. Candidate investigation includes actual iframe configuration, clipping/layout, pointer handling and browser/player behavior; a static controls setting is not proof of visibility.

Acceptance for that issue must exercise native progress, play/pause, volume, settings, CC when available, fullscreen and hover reveal. Overlay visibility/adjustment, Chinese display, list collapse, tab changes and application fullscreen/Esc must preserve native control visibility and operation. Keep the cross-origin boundary: production code must not inspect private YouTube iframe DOM. Host tests alone cannot close this real-player report; unavailable network/browser checks remain explicitly unverified.

External applicability of the custom subtitle overlay remains unresolved. The project has no recorded YouTube review or written permission establishing an exception for this overlay. Pointer pass-through and reserved control space are engineering measures, not permission evidence. A future applicability review must evaluate the actual integration against then-current official requirements; this documentation performs no policy verification or new legal assessment. Product reading behavior is in [reading spec](../product/reading-experience.md), and the remaining playback/learning scope is in [scope and evidence](../product/scope-and-acceptance.md).
