# Favorites, Questions and Content Output

Status: current behavior, updated 2026-10-21. Favorites, questions and user-saved answers share selection context while retaining independent records and editing behavior. Selection identity and first-answer bookkeeping are established engineering choices supporting this workflow.

## Selection and Relationships

Save a continuous nonblank English selection within one current subtitle entry, or the full entry. A selection's video, edition, entry and exact position identify its context; equal words in different positions or editions are not the same selection. Creating a new favorite/question requires the current version. Existing old-version records remain viewable, editable, copyable and deletable against their original context; do not draw them onto current subtitles or silently re-anchor them. Replay of old context does not publish that old revision.

A favorite has an optional personal note; “做笔记” edits that note, not another record type. Quick favorite on the same exact selection reuses the existing favorite without overwriting its note. Different positions remain distinct. Changing the selected expression requires a new record. Quick-save feedback offers undo only for a newly created favorite, never deletion of a pre-existing one. The engineering baseline auto-dismisses success after about five seconds, pausing while hovered/focused or busy/error; failed undo retains a retryable error.

Questions are independent records for a selection and may share a favorite; the same selection may have several questions. Saving a question alone does not favorite it. On the first successful nonblank answer save for each question (including creation with an answer), create/reuse its selection's favorite without overwriting a note. That is a one-time event, not a rule that answered questions must always be favorited.

Cancelling a favorite keeps questions/answers; deleting one question keeps the favorite and other questions; clearing an answer retains the favorite and makes that question unanswered. Reading/editing an existing answer or clearing/refilling it does not re-favorite a cancelled selection. A different question's first answer can favorite that selection again. Questions/answers are user-saved text, with no in-app AI call, confidence score or learning-completion state.

## Lists and Editing

Both lists cover the video's retained versions: current first, old versions identified and grouped, entries ordered by time. Favorites initially show expressions; context, note and related questions/answers have independent visibility. Questions always show expression plus question; full source sentence and answer are independently optional. Context means the full source entry, not the question's own selected expression.

Question filters are all/unanswered/answered with counts by question, not selection groups; engineering default is unanswered. A nonblank saved answer determines answered, not historical first-answer metadata or mastery. Save/clear/delete updates counts and both lists' associations. Editing protects the draft before changing filter/navigation. Association-read failures need visible retry, not a misleading empty relation.

## Copy and Markdown Export

Outputs contain learning content only, with the video title once, grouped expressions and optional fields. Expression is always included; question output always includes the question. Current defaults include source sentence and exclude note/answer/associated questions. Options are independent of screen visibility, kept across tab switches and reset on page reload. Including a favorite's answer also includes its owning question.

Single output contains only that selected record; bulk question output is strictly limited to the current filter. The same selection shares one expression/context per bulk group, but different positions with equal words never merge. Empty optional fields are omitted. Historical duplicate favorites can retain distinct notes within the requested output scope.

Do not append Prompt/Skill/practice instructions, placeholder “unfilled” content or internal time/version/source metadata. Those anchors remain stored and visible where needed in the app. Copy and UTF-8 Markdown export share the content model; Markdown escapes user text, preserves Unicode/newlines and uses a safe filename. Missing required associated data blocks the requested output with a retry route; unrequested relations need not block it. Copy/export does not change favorites, answers or first-save facts.

## Evidence

`backend/app/services/transcript_marks.py` and `transcript_questions.py` in the same directory own selection validation, favorites and first-answer behavior. `frontend/src/features/transcript/noteRelations.ts`, `ReaderCollectionPanel.tsx` and `collectionOutput.ts` own associations, filters and output. `backend/tests/test_video_api.py` covers Unicode anchors, duplicate favorites, question independence and first-answer semantics; `frontend/src/features/transcript/ReaderCollectionPanel.test.tsx` and `collectionOutput.test.ts` cover filtered output and associations. Detailed persistence/HTTP contracts live in [technical specs](../contracts/index.md).
