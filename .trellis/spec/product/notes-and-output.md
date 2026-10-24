# Expression Favorites and Agent Materials

Status: product contract, updated 2026-10-22. Cue Player supplies viewing and material collection; the user performs learning in an external Agent.

## Learning Workflow

First watch the video, then export the complete current learning transcript for the Agent to summarize and explain. Watch again after learning, favorite expressions still unclear, then separately export those expressions with their subtitle entries. The app does not enforce phases or record learning completion. These are independent exports, not a combined learning package.

## Selection and Favorites

Save a continuous nonblank English selection within one current subtitle entry, or the entire entry. Video, edition, entry and exact position identify the selection; equal words at different positions are distinct. Selecting text must not trigger sentence replay. The selection menu supports favorite and close, without note or question actions.

An exact existing selection reuses its favorite. Newly created favorites offer undo; undo never deletes a pre-existing favorite. Normal busy/error/retry and keyboard/focus behavior remain. Cancelling a favorite does not modify subtitles.

Publishing subtitles retains old favorites against their original expression and subtitle entry. Historical favorites remain viewable, replayable, exportable and removable, with their old-version identity shown in the app as needed. Do not silently re-anchor or display them as current selections.

Personal notes, questions, answers and first-answer automatic favoriting are retired. Existing note/question/answer content is intentionally removed by migration 015; favorites, including old-revision favorites, remain.

## Complete Transcript Output

The transcript tab exports the current complete learning transcript, in subtitle order, with English always included and independent choices for available Chinese and chunks. Export options are separate from on-screen reading visibility. Unprocessed subtitles export English directly without missing-content explanations or placeholders; do not generate translation or guessed chunks. Raw is not an Agent export source choice. Existing Raw/current-English SRT downloads stay in subtitle management.

## Favorite Output

The favorites tab exports saved expressions and their full containing subtitle-entry text. Do not include preceding/following entries or join fragments into complete sentences: incomplete captions are a subtitle-quality issue, not an export reconstruction task. Include both expression and original entry, without optional note/question/answer fields. Single output is limited to the requested favorite; bulk output covers the video's retained favorites. Same exact selection may be grouped, while identical text at different positions must remain distinct. Order exported favorites by video appearance, including historical favorites; never replace their context with the current edition.

## Delivery and Content

Both exports support one-click copy and UTF-8 Markdown download from their respective tabs. Copy and download share the same material model, preserve Unicode and use safe filenames and Markdown escaping where appropriate. Each output contains the video title once, without timestamps, revision/source/internal metadata, prompts, practice instructions or missing-content placeholders. The user's Agent already owns learning instructions. This prohibition does not remove the existing subtitle-processing instructions used to prepare Chinese/chunks.

Copy/export does not change favorites or publication. Empty favorites use a normal empty state instead of exporting pretend content. Clipboard/download failures remain visible and retryable. Required query failures are not equivalent to genuinely absent optional material; do not export mixed revisions or fabricate a successful read.

## Evidence Seams

Favorite persistence is owned by `backend/app/services/transcript_marks.py`, with selection/API tests in `backend/tests/test_video_api.py`. Frontend selection and output live under `frontend/src/features/transcript/`; interaction coverage includes `ReaderCollectionPanel.test.tsx`, `ReaderNotesControls.test.tsx`, `collectionOutput.test.ts` and `pages/VideoPage.test.tsx`. Source/test references locate verification seams; actual executed evidence belongs in the task. Detailed selection contracts live in [anchor contracts](../contracts/notes-and-anchors.md).
