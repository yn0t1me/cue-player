# Subtitle Preparation and Publication

Status: current behavior, updated 2026-10-22. Source-specific external processing uses one roundtrip with English chunks and Chinese translation; retired SRT/cloud paths are outside the current workflow.

## Initial Reading Subtitles

Preserve Raw as source evidence. New imports generate initial English learning subtitles locally with deterministic normalization version 2, including STT when eligible. They do not call a cloud subtitle model or automatically translate. Initial English reading is usable without external processing.

## One External Roundtrip

The app copies source-specific instructions and a verified source package. The user sends it to an external AI, pastes/selects one complete returned result, previews English/chunks/Chinese/timing, then confirms once. Source/result exchange currently uses JSON v2; ordinary users are not asked to calculate times or manually assemble its internal fields. Detailed exchange schemas belong to the [technical contracts](../contracts/source-exchange.md).

- **Manual source:** preserve each source cue's English and timing; request natural chunks and one Chinese translation per final entry. No correction, resplitting, merge or rearrangement. A cue can be a fragment, so a generic “every entry must be a complete sentence” rule does not apply here.
- **Automatic source:** request cautious correction, natural sentence boundaries, chunks and one Chinese translation per final English entry. Preserve meaning, colloquial style, fillers, meaningful repetition and self-correction. The app reconstructs timing from verified source ranges; external AI does not supply new timestamps. Chunk length guidance is a heuristic, not a mandatory word count or quality proof.
- **Unsupported evidence or STT source:** show the reason and retain the current basic English transcript. The current source-based external workflow does not support STT and does not offer retired SRT input as fallback.

A preview is not publication. Invalid/incomplete/stale results cannot replace the current revision. Confirmation atomically publishes a new revision, its segments, translation and chunk layout; failure/cancellation leaves existing reading material and Raw intact. Concurrent/current-version changes require conflict-safe handling, not silent replacement. Structure and source validation cannot prove lexical fidelity, translation quality or audio alignment: user replay and judgment remain necessary.

## Processing Rationale

External processing lets users choose their model and review semantic changes while the application owns source evidence, mechanical validation and publication. A structurally valid model result can still alter meaning, so model selection and language review remain with the user; the app does not promise automatic teaching-quality subtitles. Time reconstruction and its trade-offs are defined in [source exchange](../contracts/source-exchange.md#timing-design-rationale).

## Views, Versions and Exports

Sentence/chunk views share the same canonical English. Chunk separators are presentation metadata, not literal additions to saved English; chunks do not have invented independent playback timing. English selection anchors remain tied to the sentence text. Chinese is separate from English/chunk boundaries/selection anchors. Preview, reading list and overlay have independent Chinese toggles, off by engineering default and page-local; hiding translation neither deletes it nor requests a new one. Editions without Chinese stay English-only.

Historical revisions and their favorite context remain readable. Publishing never guesses a remapping of old selections into new sentences. No automatic deletion of retained subtitle or favorite history is defined.

Raw-derived English SRT export and current learning English SRT export remain available in subtitle management, with different sources. Separate Agent material export uses only the current learning transcript, with optional existing Chinese and chunks; its rules live in [material output](notes-and-output.md). Raw export is not guaranteed to be the exact original VTT bytes and does not read current edited English. Bilingual SRT export, legacy SRT publication, JSON v1 import and cloud run/batch/correction history are not current capabilities.

## Evidence

`frontend/src/features/transcript/chunkPrompt.ts` distinguishes manual/automatic tasks; `LearningTranscriptImportPanel.tsx` in that directory implements preview, publish, exports and historical readback. `backend/app/services/source_learning.py` and `services/transcript/source_learning.py` own evidence/reconstruction/publication; `services/transcript/normalization_service.py` owns local initial generation. See `backend/tests/test_source_learning_api.py` for manual preservation, bilingual publication, conflict/rollback and retired endpoint rejection; `test_video_api.py` for Raw export; `frontend/src/features/transcript/chunkPrompt.test.ts` for copy instructions. References describe existing evidence, not a new external acceptance run.
