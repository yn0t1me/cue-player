# Source JSON v2, Extraction and Timing

Extracted: 2026-10-21. Exact implementation: `backend/app/services/transcript/source_learning.py`; reading adapter: `backend/app/services/source_learning.py`. These engineering algorithms do not certify acoustic/semantic correctness.

## Timing Design Rationale

External AI returns source ranges and text; the application derives time from preserved source evidence. Accepting model-generated timestamps would make timing depend on copying or estimation, while whole-text similarity matching is ambiguous around repetition and changed words. Audio forced alignment adds acquisition and computation costs and is not part of this workflow. Bound source ranges make reconstruction traceable and repeatable, but cannot prove the model selected the right semantic range or preserved meaning. Display markers and cue starts are evidence, not certified acoustic word boundaries.

## Source and Result Shapes

GET learning-source is readonly, no network: {format:"learning-source-v2",source_video_id,source_digest,extractor_version,source_type,processing_mode,units}. Public source_video_id is the YouTube ID. Units expose {id,text,start_ms,time_basis}; no database UUID/local path/raw payload leaks. Limits: original source and serialized public package <=5 MiB UTF-8, <=50,000 source units. Source types are manual/automatic captions here; STT is rejected as SOURCE_TIMING_UNAVAILABLE.

POST preview strictly accepts {result:string}; result is complete JSON text, not a nested object/SRT/Markdown. Parsed root must have exactly {format:"learning-result-v2",source_video_id,source_digest,segments}. Each item has exactly string first_unit_id,last_unit_id,text,translation_zh. Digest is 64 lower-case hex and must match source/video. Result <=1 MiB UTF-8 and 1–5000 entries. Reject duplicate JSON keys, nonstandard NaN/Infinity, invalid Unicode/NUL, extra fields and empty translation. BOM/outer whitespace may be trimmed, not arbitrary code fences. Source ranges are inclusive, sequential, complete exactly once, from first to final unit; unknown/gapped/reordered/overlapping ranges reject.

Split text only on exact ` / ` separators; nonempty chunks must have no surrounding whitespace, internal whitespace is canonicalized. Canonical English joins chunks with one space; boundaries are Unicode code-point indices of those separator spaces, not UTF-16 offsets or literal slash characters. Manual unchanged text containing a literal spaced slash is preserved as one chunk. translation_zh is trimmed, nonblank and separate from English; not a chunk or anchor component.

## Source Evidence and Modes

Reader requires preserved managed VTT, verifies file path and parses the full original bytes (including whitespace-only payload rows). If all stored Raw cues match original sequence/source/time/text, use real Raw cue IDs for local evidence; otherwise use file hash/cue positions, not fabricated database IDs. Original file bytes and database Raw stay unchanged; an older file-less record cannot prove complete source through this read adapter.

Manual extractor youtube-manual-cues-v1 emits one unit per nonempty cue after display-tag/entity/whitespace normalization. One returned segment must reference one unit (first=last), English must equal that canonical source text after chunk removal, and timing is that cue's original range. Legitimate cue overlap is allowed. This is distinct from preserving original VTT bytes.

Automatic extractor youtube-vtt-units-v2 tokenizes verified original text with local cue/file/line/token/character evidence; preserves censor markers, fillers and real repetition. Internal display markers or cue starts supply clocks; they are not guaranteed acoustic word boundaries. Rolling removal needs time/echo structure, not text similarity alone. Unsupported ambiguity or illegal/reversed clocks rejects rather than drops words or repairs timing. A shared timestamp stays shared; formatting tags within a word do not create an invented extra word. Stable IDs u000001... exist only within the bound source digest/version.

## Narrow 10ms Boundary Rule

Automatic tokens strictly beyond original cue end by at most 10ms are candidates only. Require an immediately adjacent 1–10ms untimed pure suffix-echo bridge, followed exactly at bridge end by an untimed same-prefix continuation with added content; each overflow token must be in that suffix with clock exactly equal to continuation start. Preserve the original token start/text location and use continuation cue end with end_cue_sequence_index evidence. Missing bridge/extension, a gap, reversed/excess clock or simple repeated speech rejects. Equality with original cue end is not itself a permitted marker in the parser. Manual mode does not use this exception. Algorithm changes invalidate old source packages through the digest.

## Time Reconstruction

All arithmetic is integer milliseconds. Automatic sentence start = first unit.start_ms; end = min(last unit.cue_end_ms,next sentence start), or cue_end for the final entry. End at equal next start uses next_sentence_start basis. Require start>=0, start<end, end>last unit.start_ms and no automatic inter-sentence overlap. Never add a synthetic 1ms duration or split a group of shared clocks to force validity. Manual mode uses its unit's original cue end and permits source overlap.

Warnings: TEXT_CHANGED compares lexical normalized source range vs English; CUE_START_TIMING flags cue-start basis; VERY_SHORT_SEGMENT is <250ms; LONG_END_HOLD is >3000ms beyond final unit start. Warnings are review prompts, not accuracy/confidence scores. They do not prove AI chose the correct semantic range.

## HTTP Errors and Preview

SourceLearningError maps size codes to 413, SOURCE_TIMING_UNAVAILABLE/LEARNING_SOURCE_MISMATCH to 409, other domain validation to 422 (including MANUAL_TRANSCRIPT_CHANGED). Relevant codes: INVALID_SOURCE_EVIDENCE, INVALID_LEARNING_RESULT, INVALID_SOURCE_RANGE, INVALID_REBUILT_TIMING, LEARNING_SOURCE_TOO_LARGE, LEARNING_RESULT_TOO_LARGE. Do not return complete user text or file paths in messages.

Preview returns video_id,base_revision_id,preview_digest,current_segments,segments,summary,warnings,source_digest,extractor_version. Candidate entries carry sequence_index,start/end,text,translation_zh,chunks,boundary_offsets,first/last_unit_id,source_text,start_basis,end_basis. summary has current_count,candidate_count,text_changed,timing_changed,split_segment_count,chunk_count; split_segment_count currently counts candidates with chunk boundaries, not a general source-sentence split statistic. warnings carry code/sequence_index/start/end/message. Shape types: `backend/app/schemas/source_learning.py`.

Evidence: `backend/tests/test_source_learning.py`, `test_source_learning_api.py`, `frontend/src/features/transcript/chunkPrompt.ts` and `chunkPrompt.test.ts` (same directory). [Publication](publication.md) defines digest identity and atomic confirmation; linguistic quality and long-pause listening remain separate acceptance.
