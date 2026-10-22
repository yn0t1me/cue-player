# Reading Experience

Status: current behavior, updated 2026-10-21. Transcript, favorites and questions share one workspace beside the player. Exact geometry and controls below are the established engineering baseline.

## Playback and Transcript

The reader combines a YouTube player with an independently scrollable transcript/workspace, aligned to the player height on desktop and stacked with independent scrolling on narrow screens. Sentence clicks seek to the sentence start and play when the player is ready. Selecting text or operating editing controls must not be interpreted as replay. Highlight the current sentence from actual player time; subtitle gaps do not display a fabricated previous sentence. Auto-follow can pause for manual scrolling and resume via the return-to-current action. While following, center the current sentence where scroll bounds allow without artificial blank space at the start/end.

Sentence and chunk reading modes share English text, sentence replay, highlight and selection. A missing/mismatched layout cannot enable guessed chunks; explain how to process subtitles. A current version change updates reading data without moving old note anchors.

## One Workspace, Three Tabs

Transcript, favorites and questions occupy the same workspace with a stable outer frame. Tab switching preserves each panel's reading position and the existing player/time/play state. The historical marks URL enters the same video's favorites tab; it is not a second marks-page application. Old standalone-page “return paused” behavior is historical, not the current tab-switch rule.

Editing a note/question/answer preserves draft and selection, suspends transcript auto-follow and does not automatically pause video. Navigation, switching editors/tabs or closing a dirty editor must resolve unsaved drafts; save failure retains input. A concurrent subtitle change preserves the original anchor/draft rather than attaching it to a new sentence. Selection menus/editor placement do not push later transcript sentences around. Preserve keyboard access, Escape for a clean menu and return focus to its trigger.

## Overlay and Fullscreen

An application overlay displays the current learning sentence; the established defaults show the overlay and the list. It shares sentence/chunk mode with the list and has its own Chinese toggle. Subtitle visibility, list visibility, size/position controls and translation settings are page-local, not saved learning progress. Hiding the overlay does not stop list synchronization; hiding the list does not stop the overlay. Oversized full English/Chinese content docks beneath the video instead of dropping text or fabricating new timing.

The app's fullscreen action includes the video and learning overlay/control container; it is distinct from YouTube native fullscreen. Preserve native player controls and report fullscreen failure while leaving ordinary viewing usable. Exiting fullscreen does not intentionally seek/play/pause; draft and list visibility are retained. Overlay text normally passes through playback clicks; adjustment mode supports bounded drag/keyboard movement and reset. Selection/note actions remain in the full transcript list, not the overlay. Chinese display is separate from English interaction: Chinese text does not trigger English selection or sentence replay.

Historical successful browser checks are version/scenario-specific. The deferred Chrome native-control disappearance issue and unresolved external policy question are not newly fixed or verified here; see [scope and evidence](scope-and-acceptance.md).

## Evidence

`frontend/src/pages/VideoPage.tsx`, `frontend/src/features/transcript/ReadingNotesWorkspace.tsx`, `TranscriptPanel.tsx` and `ReaderNotesControls.tsx` in that feature directory, `frontend/src/features/video/LearningPlayer.tsx` and `YouTubePlayer.tsx`, and `frontend/src/App.tsx` implement these boundaries. Test references: `frontend/src/pages/VideoPage.test.tsx`, `frontend/src/features/transcript/ReaderNotesControls.test.tsx`, `TranscriptPanel.test.tsx`, and `frontend/src/features/video/LearningPlayer.test.tsx`. Mocked player/browser tests do not prove live YouTube behavior.
