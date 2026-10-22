# Initial Transcript and Media Contracts

Extracted: 2026-10-21. Internal service seams and initial generation only; external source processing is in [source exchange](source-exchange.md).

## Adapter and Source Boundaries

`backend/app/services/youtube/parser.py` parses public URL identity; metadata/caption adapters return internal DTOs, not ORM or frontend objects. CaptionCandidate includes source,language,language_name,url,extension. Selection filters native English family VTT, excludes tlang translation URLs, ranks manual before automatic for manual_first, and only automatic for auto_only; language order en, en-orig, en-us, en-gb then other normalized English variants and original discovery order. Only a successful discovery with no eligible candidate enters STT; discovery/download/parse failures stay errors.

Caption download verifies WEBVTT and a 5 MiB bound; CaptionStore atomically saves raw/caption.vtt under the internal video UUID. `backend/app/services/transcript/vtt.py` parse_vtt preserves cue text/lines, identifier and millisecond times in Raw, with original source_payload; allows source overlap and zero-length cue but rejects negative/nonfinite/reversed ranges. webvtt-py may omit whitespace-only payload cues: source-exchange uses a separate readonly parser of the preserved file rather than rewriting stored Raw.

STT adapter `backend/app/services/transcript/stt.py` uses local_files_only model loading and explicit English, configured VAD and word_timestamps. Model load/transcribe/lazy iteration and mapping happen in a worker thread. Frozen TranscriptionData/segment/word DTOs isolate third-party objects. Persist cues and actual words in one stage handoff; absent word times/confidence stay null, invalid ordering/values reject the batch. Current initial normalization still uses cue refs, not interpolated word alignment.

## Deterministic Version 2

TranscriptNormalizationService.normalize(RawTranscriptEvidence) returns NormalizationOutcome(segments,run), no cloud provider seam. TranscriptNormalizer strips display tags, unescapes entities and collapses whitespace; it does not correct lexical text. Empty text is skipped; sequence_index is reassigned continuously.

- Generic rolling expansion requires overlapping time and a strict previous-text-plus-space prefix; unrelated overlaps and identical repeated speech stay.
- Adjacent auto-style rolling evidence uses short cue duration <=0.05s, gap 0–0.05s and strict prefix extension. Recognized groups also require their relative gap within -0.05–0.05s, then use case-insensitive longest suffix/prefix overlap; new words can start a new segment at punctuation/length limits using original cue timing, not synthetic word timing.
- Ordinary nonoverlap fragments merge only with gap 0–0.35s, no ending sentence punctuation, prior length <=120, joined length <=160 and unequal text. Those are merge heuristics, not universal final segment length limits. A multi-sentence cue is not split using invented times.
- Output keeps ordered source cue IDs and the covered source timing; actual gaps remain gaps.

`backend/app/services/transcript/normalizer.py` is the exact branch/threshold authority; `normalization_core.py` supplies immutable evidence/validation. Initial publication in JobManager validates segment refs belong to that video, refuses preexisting learning/run/current pointer, then creates deterministic run (method,version2,input_unit_count), generated revision1, segments, ready/completed/100 in one transaction. The run's job_id is unique. No old model/batch/correction structures are written.

## Managed Media

`backend/app/services/processing/audio_store.py` owns canonical internal UUID paths and containment/symlink checks; audio uses a unique .download-{UUID} staging directory and source.{safe-extension} final artifact. finalize verifies expected target, file location/type/size/readability then atomically hands off; cleanup removes only managed files/staging and preserves unrelated files and other videos. CaptionStore validates canonical UUID and atomic replace; additional source-read/retry checks reject symlink escape. Do not claim every store method has identical symlink hardening.

`backend/app/services/processing/audio_acquisition.py` coordinates download and discard on failure/cancellation; YouTube audio adapter requests audio only, not a saved full video. Pipeline cleans managed audio on terminal paths and startup handles leftovers. Model cache is setup-owned and not terminal audio cleanup. Settings/STT preparation remain in [engineering baseline](../guides/project-engineering.md).

Evidence: `backend/tests/test_youtube_captions.py`, `test_vtt_transcript.py`, `test_normalization_service.py`, `test_normalization_core.py`, `test_transcript_normalizer.py`, `test_stt_transcript.py`, `test_audio_store.py`, `test_video_import_pipeline.py`. Inspection of those tests is not new network/model execution.

## Internal DTO and Service Seams

These are internal shapes, not additional HTTP payloads. Read the symbol definitions before extending them.

| Seam | Current input/output |
|---|---|
| youtube.metadata.fetch_metadata | async URL -> YouTubeMetadata(video_id,title,channel_title,duration,thumbnail_url) |
| youtube.captions.discover_captions / select_best_caption | async URL -> candidates; pure (candidates,preference) -> candidate or None |
| youtube.audio.download_audio / AudioAcquirer.acquire | async (URL,output template) -> DownloadedAudio(path,extension,format_id,audio_codec); acquire(internal ID,URL) -> AudioArtifact(path,extension,size_bytes) |
| FasterWhisperTranscriber.transcribe | async local path -> TranscriptionData(language,language_probability,duration_seconds,duration_after_vad_seconds,segments) |
| STT segment / word | segment has sequence_index,start/end,text,words,source_payload; word has text,nullable start/end/confidence |
| RawTranscriptEvidence | source,language,cue tuple,optional word tuple; no provider/model/result history |
| TranscriptNormalizationService.normalize | async evidence -> immutable NormalizationOutcome(segment tuple,run); run has deterministic method/version/input count |
| VideoImportPipeline.run | async (internal video ID,job ID); stage coordination owns no request Session |

Definitions: `backend/app/services/youtube/metadata.py`, `backend/app/services/youtube/audio.py`, `backend/app/services/processing/audio_acquisition.py`, `backend/app/services/transcript/stt.py`, `backend/app/services/transcript/normalization_core.py`, `backend/app/services/transcript/normalization_service.py` and `backend/app/services/processing/video_import.py`. No third-party segment/model object or filesystem path is part of the ordinary reading API.
