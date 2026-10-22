# Current Technical Contracts

Updated: 2026-10-21. These are current application contracts, not new implementation authorization or runtime acceptance. Product intent and scope live in [product specs](../product/index.md); coding conventions live in the frontend/backend indexes.

## Load by Boundary

| Change | Read |
|---|---|
| HTTP route, response or common error | [HTTP API](http-api.md) |
| Tables, relationships, revisions, constraints | [Data model](data-model.md) |
| Selection positions, favorites or questions | [Notes and anchors](notes-and-anchors.md) |
| Collections, previews or batch submission | [Collections and batches](collections-and-batches.md) |
| Job transitions, restart or explicit retry | [Processing and retries](processing-and-retries.md) |
| Initial subtitles, external adapters, temporary media | [Transcript pipeline](transcript-pipeline.md) |
| Source JSON v2, extraction and timing | [Source exchange](source-exchange.md) |
| Preview confirmation, digests or atomic publication | [Publication](publication.md) |
| Browser/player timing, lifecycle, selection, fullscreen | [Player](player.md) |

Read both sides for cross-layer changes. HTTP field types are implemented by backend/app/schemas, persisted shapes by backend/app/db/models, and operation rules by the referenced services; disagreement with an effective decision must be recorded, not silently normalized to existing code. These contracts distinguish established engineering choices from explicitly confirmed product behavior; not every field was individually approved by the user.

Future in-app learning LLM tasks, source-switch/ready-video Reprocess, STT-based source alignment and chapter/learning-set/practice contracts remain outside current contracts. [Product scope](../product/scope-and-acceptance.md) records deferred and unspecified behavior; [player limits](player.md#evidence-and-unresolved-limits) records browser acceptance and external applicability limitations. Source/test references locate verification seams and do not assert a new successful run. Development requires no archived design or task records.
